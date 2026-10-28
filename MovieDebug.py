# Christopher Mee
# 2026-10-20
# ParseTorrentName (PTN) and ParseTorrentListToCSV debugging tools.
# Used to overcome bad input parsing and bad API data responses.

import os  # System utilities
import pickle  # read rerun output
import re  # Extract URL
import subprocess  # Re-run and debug torrent names
import sys  # System
import tempfile  # Temp files for subprocess IPC
import time  # fix out of order open urls
import webbrowser  # Open url in browser
from pathlib import Path  # File path handling

import pandas as pd  # Pandas (dataframes)

from ConsoleDebug import ConsoleDebug  # print and clear console output


class MovieDebug:
    TAB_OPEN_DELAY = 0.1
    SKIP_WAIT = True
    IMDB_COL = "IMDB"

    def __init__(
        self,
        consoleInput,
        *,
        isArgumentPresent,
        extractMovieTags,
        extractExcessMovieTags,
        UPPERCASE_CSV_HEADERS=True,
        MATCH_TEXT_FILE_INDEX=True,
        LEFT_JUSTIFY_DEBUG_OUTPUT=True,
        FILTER_PTN_DEBUG_OUTPUT=True,
        NA_REPLACEMENT_DEBUG_OUTPUT="",
        FILE_PATH,
        TEXT_FILE_ARGUMENT,
        APPENDING,
        HYPERLINK_STYLE,
        DEBUGGING,
        APPENDING_ARGUMENT_OFFSET,
        HYPERLINK_ARGUMENT_OFFSET,
        DEBUGGING_ARGUMENT_OFFSET,
        EXCEL_HYPERLINK,
    ):
        # initialize parameters
        self.consoleInput = consoleInput
        self.isArgumentPresent = isArgumentPresent
        self.extractMovieTags = extractMovieTags
        self.extractExcessMovieTags = extractExcessMovieTags
        self.UPPERCASE_CSV_HEADERS = UPPERCASE_CSV_HEADERS
        self.MATCH_TEXT_FILE_INDEX = MATCH_TEXT_FILE_INDEX
        self.LEFT_JUSTIFY_DEBUG_OUTPUT = LEFT_JUSTIFY_DEBUG_OUTPUT
        self.FILTER_PTN_DEBUG_OUTPUT = FILTER_PTN_DEBUG_OUTPUT
        self.NA_REPLACEMENT_DEBUG_OUTPUT = NA_REPLACEMENT_DEBUG_OUTPUT
        self.FILE_PATH = FILE_PATH
        self.TEXT_FILE_ARGUMENT = TEXT_FILE_ARGUMENT
        self.APPENDING = APPENDING
        self.HYPERLINK_STYLE = HYPERLINK_STYLE
        self.DEBUGGING = DEBUGGING
        self.APPENDING_ARGUMENT_OFFSET = APPENDING_ARGUMENT_OFFSET
        self.HYPERLINK_ARGUMENT_OFFSET = HYPERLINK_ARGUMENT_OFFSET
        self.DEBUGGING_ARGUMENT_OFFSET = DEBUGGING_ARGUMENT_OFFSET
        self.EXCEL_HYPERLINK = EXCEL_HYPERLINK

        # initialize variables
        self.inputTextFilePath = None

    def dfToStringLJust(self, df, naRep="NaN", index=True):
        dfFilled = df.fillna(naRep)
        widths = {
            col: max(len(str(col)), dfFilled[col].astype(str).str.len().max())
            for col in dfFilled.columns
        }

        def makeFmt(w):
            def fmt(x):
                return f"{str(x):<{w}}"

            return fmt

        formatters = {col: makeFmt(w) for col, w in widths.items()}
        return dfFilled.to_string(justify="left", formatters=formatters, index=index)

    def dfToString(self, df):
        return (
            self.dfToStringLJust(df, naRep=self.NA_REPLACEMENT_DEBUG_OUTPUT)
            if self.LEFT_JUSTIFY_DEBUG_OUTPUT
            else df.to_string(na_rep=self.NA_REPLACEMENT_DEBUG_OUTPUT)
        )

    def promptRowCorrection(self, parsedMovies, debugOut, refreshTable=None):
        result = self.consoleInput.promptRowSelection(parsedMovies, debugOut)
        if result is None:
            return  # cancel
        rowSelection, firstRow = result
        rowSelectionLabel = parsedMovies.index[rowSelection - firstRow]

        titleCol = next(col for col in parsedMovies.columns if col.lower() == "title")
        yearCol = next(col for col in parsedMovies.columns if col.lower() == "year")
        oldTitle = parsedMovies.loc[rowSelectionLabel, titleCol]
        oldYear = parsedMovies.loc[rowSelectionLabel, yearCol]

        # row new title input
        newTitle = input(
            self.consoleInput.formatPrompt(
                'New title (blank to keep "{oldTitle}"): ', oldTitle=oldTitle
            )
        ).strip()

        # row new year input
        yearPrompt = self.consoleInput.formatPrompt(
            "New year (blank to keep {oldYear}): ", oldYear=oldYear
        )
        newYearStr = input(yearPrompt).strip()
        while newYearStr:
            try:
                parsedMovies.loc[rowSelectionLabel, yearCol] = int(newYearStr)
                break
            except ValueError:
                newYearStr = debugOut.reAskSameLine(yearPrompt)

        if newTitle:
            parsedMovies.loc[rowSelectionLabel, titleCol] = newTitle

        print(
            "\n"
            + self.consoleInput.formatPrompt(
                "Row {rowIndex} Old - Title, Year: {title}, {year}",
                rowIndex=rowSelection,
                title=oldTitle,
                year=oldYear,
            )
            + "\n"
            + self.consoleInput.formatPrompt(
                "Row {rowIndex} New - Title, Year: {title}, {year}",
                rowIndex=rowSelection,
                title=parsedMovies.loc[rowSelectionLabel, titleCol],
                year=parsedMovies.loc[rowSelectionLabel, yearCol],
            )
            + "\n"
        )

    def screenDebugTable(
        self,
        parsedMovies,
        debugTitle,
        buildDfDebug=None,
        debugPrompt="Clear debug output and continue? Or edit row? [Y/N/E]:",
        onEditSelection=None,
    ):
        if onEditSelection is None:
            onEditSelection = self.promptRowCorrection

        debugOut = ConsoleDebug()

        if self.UPPERCASE_CSV_HEADERS:
            debugTitle = debugTitle.upper()
            debugPrompt = debugPrompt.upper()

        def printTable():
            dfDebug = (
                buildDfDebug(parsedMovies) if buildDfDebug else parsedMovies.copy()
            )

            if self.MATCH_TEXT_FILE_INDEX:
                dfDebug.index = dfDebug.index + 1

            if self.UPPERCASE_CSV_HEADERS:
                dfDebug.columns = dfDebug.columns.str.upper()

            debugOut.print(f"{debugTitle}\n\n" + self.dfToString(dfDebug))

        while True:
            printTable()

            # prompt user to continue, exit, or edit a row. Long dfs cause the
            # console to scroll down. Auto scroll back up, so df rows can be
            # screened from top to bottom.
            choice = debugOut.autoScrollThenChoose(f"\n{debugPrompt} ")
            while choice not in ("y", "n", "e"):
                choice = debugOut.reAskSameLine(f"\n{debugPrompt} ")

            if choice == "y":
                debugOut.clear()
                return
            if choice == "n":
                sys.exit(0)
            # choice == "e":
            if self.SKIP_WAIT == onEditSelection(parsedMovies, debugOut, printTable):
                debugOut.clear()
                continue

            debugOut.waitForAnyKey()
            debugOut.clear()

    def buildPtnFilterDfDebug(self, parsedMovies):
        dfDebug = parsedMovies[["year", "title", "episodeName", "excess"]]

        if self.FILTER_PTN_DEBUG_OUTPUT:
            # Filter out known bad values. The displayed output will still have
            # known good values, so be careful when screening for bad values.
            if parsedMovies["episodeName"].notna().any():
                dfDebug["episodeName"] = self.extractMovieTags(
                    parsedMovies, "episodeName", useColNameAsTag=False, formatTags=False
                )

            # Filter out whitelisted Excess tags here
            # Display str as single str and multi-str as list
            if parsedMovies["excess"].notna().any():
                dfDebug["excess"] = self.extractExcessMovieTags(
                    parsedMovies, formatted=False, returnLists=True, invert=True
                ).map(
                    lambda tags: (
                        tags[0] if isinstance(tags, list) and len(tags) == 1 else tags
                    )
                )

        return dfDebug

    def ptnFilterDebug(self, parsedMovies):
        self.screenDebugTable(
            parsedMovies,
            debugTitle="Tag Filter Screening:",
            buildDfDebug=self.buildPtnFilterDfDebug,
        )

    def extractUrl(self, text):
        if not isinstance(text, str):
            return None
        match = re.search(r'https?://[^\s"\'<>\]\)]+', text)
        if not match:
            return None
        return match.group(0).rstrip(".,;")

    def openUrl(self, url):
        if url:
            webbrowser.open_new_tab(url)

    def buildUrlListFromDf(self, parsedMovies, IMDbCol):
        return [self.extractUrl(cellValue) for cellValue in parsedMovies[IMDbCol]]

    def openAllUrlsFromDf(self, parsedMovies, IMDbCol):
        tabOpenDelay = self.TAB_OPEN_DELAY
        firstUrl = True
        for url in self.buildUrlListFromDf(parsedMovies, IMDbCol):
            if url:
                if not firstUrl:
                    time.sleep(tabOpenDelay)
                self.openUrl(url)
                firstUrl = False

    def promptOpenIMDbUrl(self, parsedMovies, debugOut):
        result = self.consoleInput.promptRowSelection(
            parsedMovies, debugOut, allowAll=True
        )
        if result is None:
            return

        selectedIndex, firstRow = result
        if selectedIndex == self.consoleInput.ALL_ROWS:
            self.openAllUrlsFromDf(parsedMovies, self.IMDB_COL)
            return

        selectedRowIndex = parsedMovies.index[selectedIndex - firstRow]
        IMDbUrl = self.extractUrl(parsedMovies.loc[selectedRowIndex, self.IMDB_COL])
        self.openUrl(IMDbUrl)

    def getTorrentNameFromFile(self, textFilePath, fileLineNumber):
        with open(textFilePath, encoding="utf-8") as f:
            for currentLineNumber, line in enumerate(f, start=1):
                if currentLineNumber == fileLineNumber:
                    return line.rstrip("\r\n")
        return None

    def promptRerunMovieWithSearchYearFallback(self, parsedMovies, debugOut):
        # prompts and titles
        debugOnRerunPrompt = (
            "Enable debugging for the re-run search? (Y/N, blank to skip): "
        )
        rerunPromptTitle = "\nRe-running line {lineIndex} with search-year fallback:"

        # keep changes msg's
        rerunDiscardedResult = "\nNo changes were made!"
        rerunAcceptedResult = "\nUpdated row {lineIndex} successfully!"

        # error msg's
        fileReadError = (
            "\nCould not read line {lineIndex} from input file. No changes were made."
        )
        rerunFailedToLaunch = "\nFailed to launch re-run debug session: {e}"
        rerunNoResult = "\nRe-run did not produce a result. No changes were made."
        rerunInvalidResult = (
            "\nRe-run produced an invalid result. No changes were made."
        )

        # row selection
        if not (result := self.consoleInput.promptRowSelection(parsedMovies, debugOut)):
            return
        rowIndexStr, firstRow = result

        # debug selection
        debugSelection = self.consoleInput.promptYesNo(
            debugOnRerunPrompt, debugOut, blankMeansNo=True
        )

        # get original torrent name
        lineIndex = (
            int(rowIndexStr) if self.MATCH_TEXT_FILE_INDEX else int(rowIndexStr) + 1
        )
        try:
            torrentName = self.getTorrentNameFromFile(self.inputTextFilePath, lineIndex)
        except OSError:
            torrentName = None

        if not torrentName:
            print(self.consoleInput.formatPrompt(fileReadError, lineIndex=lineIndex))
            return

        # save old row
        oldDfIndex = parsedMovies.index[int(rowIndexStr) - firstRow]
        oldRowData = parsedMovies.loc[oldDfIndex]

        # create temp file used to send and receive data from the subprocess.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmpFile:
            tmpFile.write(
                torrentName if torrentName.endswith("\n") else torrentName + "\n"
            )
            tmpPath = tmpFile.name

        # run re-run subprocess
        scriptPath = str(Path(sys.argv[self.FILE_PATH]).resolve())
        print(self.consoleInput.formatPrompt(rerunPromptTitle, lineIndex=lineIndex))
        try:
            # set subprocess arguments
            append = "false"  # cannot append, required step to import result
            linkStyle = (
                self.EXCEL_HYPERLINK
                if self.isArgumentPresent(
                    self.HYPERLINK_ARGUMENT_OFFSET, self.EXCEL_HYPERLINK
                )
                else "None"
            )
            debugOnRerun = "true" if debugSelection else "false"

            subprocess.Popen(
                [sys.executable, scriptPath, "--rerun", tmpPath, tmpPath]
                + [append, linkStyle, debugOnRerun],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            ).wait()
        except Exception as e:
            print(self.consoleInput.formatPrompt(rerunFailedToLaunch, e=e))
            try:
                os.unlink(tmpPath)
            except OSError:
                pass
            return

        # read the subprocess output
        try:
            newRow = pd.read_pickle(tmpPath)
        except (OSError, EOFError, pickle.UnpicklingError, ValueError):
            print(self.consoleInput.formatPrompt(rerunNoResult))
            return
        finally:
            try:
                os.unlink(tmpPath)
            except OSError:
                pass

        if not isinstance(newRow, pd.DataFrame):
            print(self.consoleInput.formatPrompt(rerunInvalidResult))
            return

        if newRow.empty:
            print(self.consoleInput.formatPrompt(rerunNoResult))
            return
        if len(newRow) != 1 or not newRow.columns.equals(parsedMovies.columns):
            print(self.consoleInput.formatPrompt(rerunInvalidResult))
            return
        newRowData = newRow.iloc[0]

        # display old vs new
        dfCompare = pd.DataFrame(
            [oldRowData.values, newRowData.values],
            index=["OLD", "NEW"],
            columns=newRow.columns,
        )
        print(self.dfToString(dfCompare))

        # confirm before applying
        if not self.consoleInput.promptYesNo(
            "\nApply these changes? [Y/N]: ", debugOut
        ):
            print(self.consoleInput.formatPrompt(rerunDiscardedResult))
            return

        # apply new row data, overwriting old data
        parsedMovies.loc[oldDfIndex] = newRowData.values

        print(self.consoleInput.formatPrompt(rerunAcceptedResult, lineIndex=lineIndex))

    def promptOptionsMenu(self, parsedMovies, callerDebugOut, refreshTable=None):
        dout = ConsoleDebug()

        optionsTitle = "Debug Options:"
        optionsList = [
            ("Open IMDb URL(s)", lambda: self.promptOpenIMDbUrl(parsedMovies, dout)),
            ("Edit row", lambda: self.promptRowCorrection(parsedMovies, dout)),
            (
                "rerun row using original torrent name with TMDb search-year fallback",
                lambda: self.promptRerunMovieWithSearchYearFallback(parsedMovies, dout),
            ),
        ]
        firstOption = 1
        lastOption = firstOption + len(optionsList) - 1

        optionsMenu = (
            "\n"
            + optionsTitle
            + "\n"
            + "\n".join(
                f"{number}) {label}"
                for number, (label, _) in enumerate(optionsList, start=firstOption)
            )
            + "\n"
        )
        optionsPrompt = "Select option ({firstOption}-{lastOption}, blank to exit): "

        # format options prompts
        formattedMenu = self.consoleInput.formatPrompt(optionsMenu)
        formattedPrompt = self.consoleInput.formatPrompt(
            optionsPrompt, firstOption=firstOption, lastOption=lastOption
        )

        while True:
            # print options menu
            dout.print(formattedMenu)

            # options menu input
            selectionStr = self.consoleInput.promptNumberInRange(
                formattedPrompt, dout, firstOption, lastOption
            )
            if not selectionStr:
                dout.clear()
                return self.SKIP_WAIT

            # process selection
            selection = int(selectionStr)
            _, onSelection = optionsList[selection - firstOption]
            onSelection()

            dout.waitForAnyKey()
            dout.clear()
            if refreshTable is not None:
                callerDebugOut.clear()
                refreshTable()

    def finalOutputDebug(self, parsedMovies, inputTextFilePath):
        self.inputTextFilePath = inputTextFilePath
        self.screenDebugTable(
            parsedMovies,
            debugTitle="\n" + "Final Output Screening:",
            onEditSelection=self.promptOptionsMenu,
            debugPrompt="Clear debug output and finish? Or edit row? [Y/N/E]:",
        )
