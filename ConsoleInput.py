# Christopher Mee
# 2026-10-19
# Reusable console prompts

import string  # String formatting


class ConsoleInput:
    BLANK = ""
    ALL_ROWS = "all"
    ALLOW_ALL_INPUT = ("a", ALL_ROWS)

    def __init__(self, UPPERCASE_CSV_HEADERS=False, MATCH_TEXT_FILE_INDEX=False):
        self.UPPERCASE_CSV_HEADERS = UPPERCASE_CSV_HEADERS
        self.MATCH_TEXT_FILE_INDEX = MATCH_TEXT_FILE_INDEX

    def formatPrompt(self, template, **values):
        # format a user prompt, uppercasing the template's static text but not the
        # interpolated values when UPPERCASE_CSV_HEADERS is set.
        if self.UPPERCASE_CSV_HEADERS:
            parts = []
            for literal, field, spec, conversion in string.Formatter().parse(template):
                parts.append(literal.upper())
                if field is not None:
                    parts.append("{" + field)
                    if conversion:
                        parts.append("!" + conversion)
                    if spec:
                        parts.append(":" + spec)
                    parts.append("}")
            template = "".join(parts)
        return template.format(**values)

    def promptYesNo(self, prompt, debugOut, blankMeansNo=False):
        # return True for yes, False for no, or "" when blank
        answer = input(prompt).strip().lower()
        if blankMeansNo and self.BLANK == answer:
            return False
        while answer not in ("y", "n"):
            answer = debugOut.reAskSameLine(prompt).strip().lower()
            if blankMeansNo and self.BLANK == answer:
                return False
        return answer == "y"

    def promptNumberInRange(
        self, prompt, debugOut, firstOption, lastOption, extraChoices=()
    ):
        # return the entered number/choice string, or "" when blank
        selectionStr = input(prompt).strip().lower()
        while selectionStr and not (
            selectionStr in extraChoices
            or (
                selectionStr.isdecimal()
                and firstOption <= int(selectionStr) <= lastOption
            )
        ):
            selectionStr = debugOut.reAskSameLine(prompt).strip().lower()
        return selectionStr

    def promptRowSelection(self, parsedMovies, debugOut, allowAll=False):
        # return (rowIndex, firstRow), ("all", firstRowIndex),
        # or None on cancel
        firstRowIndex = 1 if self.MATCH_TEXT_FILE_INDEX else 0
        lastRow = firstRowIndex + len(parsedMovies) - 1
        rowPrompt = self.formatPrompt(
            "Row number ({firstRow}-{lastRow}, {allOption}blank to cancel): ",
            firstRow=firstRowIndex,
            lastRow=lastRow,
            allOption="A for all, " if allowAll else "",
        )

        # row index input
        print()  # single newline, not printed on re-ask
        rowIndexStr = self.promptNumberInRange(
            rowPrompt,
            debugOut,
            firstRowIndex,
            lastRow,
            extraChoices=self.ALLOW_ALL_INPUT if allowAll else (),
        )

        if not rowIndexStr:
            return None

        rowIndex = (
            self.ALL_ROWS if rowIndexStr in self.ALLOW_ALL_INPUT else int(rowIndexStr)
        )
        return (rowIndex, firstRowIndex)
