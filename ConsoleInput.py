# Christopher Mee
# 2026-10-19
# Reusable console prompts

import string  # String formatting


class ConsoleInput:
    BLANK = ""

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
        # return 'y', 'n', or "" when blank
        answer = input(prompt).strip().lower()
        if blankMeansNo and self.BLANK == answer:
            return False
        while answer not in ("y", "n"):
            answer = debugOut.reAskSameLine(prompt)
            if blankMeansNo and self.BLANK == answer:
                return False
        return answer == "y"

    def promptNumberInRange(self, prompt, debugOut, firstOption, lastOption):
        # return the entered number string, or "" when blank
        selectionStr = input(prompt).strip()
        while selectionStr and not (  # valid
            selectionStr.isdigit() and firstOption <= int(selectionStr) <= lastOption
        ):
            selectionStr = debugOut.reAskSameLine(prompt)
        return selectionStr

    def promptRowSelection(self, parsedMovies, debugOut):
        # return (rowIndex, firstRow), or None on cancel
        firstRowIndex = 1 if self.MATCH_TEXT_FILE_INDEX else 0
        lastRow = firstRowIndex + len(parsedMovies) - 1
        rowPrompt = self.formatPrompt(
            "Row number ({firstRow}-{lastRow}, blank to cancel): ",
            firstRow=firstRowIndex,
            lastRow=lastRow,
        )

        # row index input
        print()  # single newline, not printed on re-ask
        rowIndexStr = self.promptNumberInRange(
            rowPrompt, debugOut, firstRowIndex, lastRow
        )

        if not rowIndexStr:
            return None

        rowIndex = int(rowIndexStr)
        return (rowIndex, firstRowIndex)
