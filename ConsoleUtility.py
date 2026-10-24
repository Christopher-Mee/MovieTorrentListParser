# Christopher Mee
# 2026-10-20
# Generic console utilities


def printProgress(
    progress, *, sign="%", progressMsg="Complete", showProgressBar=True, barWidth=20
):
    MAX_PERCENTAGE = 100
    MIN_PERCENTAGE = 0

    if not MIN_PERCENTAGE <= progress <= MAX_PERCENTAGE:
        raise ValueError(
            f"progress must be between {MIN_PERCENTAGE} and {MAX_PERCENTAGE}"
        )

    percentComplete = str(int(progress))

    if showProgressBar:  # [====================]%100 Complete
        if not isinstance(barWidth, int) or barWidth <= 0:
            raise ValueError("barWidth must be a positive integer")

        # progress bar
        barCellSize = MAX_PERCENTAGE / barWidth
        cellCount = int(progress / barCellSize)
        bar = " " + "[" + "=" * cellCount + " " * (barWidth - cellCount) + "]"

        # status message
        status = f"{percentComplete} {progressMsg}"
        maxStatusWidth = len(str(MAX_PERCENTAGE) + " " + progressMsg)

        print(f"{bar}{sign}{status: >{maxStatusWidth}}", end="\r", flush=True)
    else:  # 100% Complete
        maxStatusWidth = len(str(MAX_PERCENTAGE))
        print(
            f"{percentComplete: >{maxStatusWidth}}{sign} {progressMsg}",
            end="\r",
            flush=True,
        )
