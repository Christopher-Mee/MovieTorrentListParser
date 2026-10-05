# Christopher Mee
# 2023-08-16
# Parse and convert a list of p2p movie file names into CSV format
import re  # Regex
import sys  # System
from difflib import SequenceMatcher  # Str compare/search tool
from enum import Enum, auto  # Ternary return solution
from pathlib import Path  # File path handling

import numpy as np  # Numpy
import pandas as pd  # Pandas (dataframes)
import PTN  # parse-torrent-title
import pycountry  # Movie languages
import pyperclip  # Pyperclip

import tmdbClient as tmdb  # TMDB API
from ConsoleDebug import ConsoleDebug  # Debugging output

# SETTINGS #####################################
# CSV Headers
UPPERCASE_CSV_HEADERS = True

# Movie title
COMBINE_DEFAULT_FOREIGN_TITLES = True

# Tags
ADD_TAGS_TO_TITLE = True
UPPERCASE_TAGS = True
ADD_SPACE_BETWEEN_TAGS = True

# Excess Tags
COMBINE_RELEASE_AND_EXCESS_TAGS = True
FORMAT_EXCESS_TAGS_IN_RELEASE = True

# Debugging
MATCH_TEXT_FILE_INDEX = True
LEFT_JUSTIFY_DEBUG_OUTPUT = True
FILTER_PTN_DEBUG_OUTPUT = True
NA_REPLACEMENT_DEBUG_OUTPUT = ""

# English Foreign combined title splitter
FOREIGN_MOVIE_SPLITTER = " AKA "

# Language
# default lang not shown as a tag, only foreign langs
DEFAULT_LANGUAGE = "English"
DEFAULT_COUNTRY = "US"

# TMDb Language code manual patches
LANG_PATCHES_TMDB = {"cn": "Cantonese"}

# Title similarity threshold
THRESHOLD = 0.78

# Tag classification, order, and filtering
# determines output order
BOOL_TAG_COLS = ["unrated", "directorsCut", "extended"]
STR_TAG_COLS = ["episodeName"]
EXCESS_TAG_COLS = ["excess"]

# determines output order
TAG_AND_HEADER_LABELS = {
    "unrated": "Unrated",
    "directorsCut": "Director's Cut",
    "extended": "Extended",
    "episodeName": "Other Version",
    "excess": "Excess",
}

EXCESS_TAG_WHITELIST = {
    "35mm Scan": ["35mm", "Scan", "Celluloid"],
    "DCP": ["DCP"],
    "ProRes": ["PRORES"],
}
EPISODE_NAME_TAG_BLACKLIST = {"Hybrid"}
ALT_TITLE_TYPE_KEYWORDS_BLACKLIST = [
    keyword.lower() for keyword in ["informal", "alternative"]
]
################################################


def log_error(title, year, filename="INCOMPLETE_MOVIES.txt"):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"{title}\t{year}\n")


def isArgumentPresent(OFFSET, VALID_ARGUMENT):
    return (
        len(sys.argv) >= MINIMUM_ARGUMENT_COUNT + OFFSET
        and sys.argv[(TEXT_FILE_ARGUMENT + OFFSET)].lower() == VALID_ARGUMENT
    )


def isTextFile(str):
    pattern = r"\.txt$"
    return re.search(pattern, str)


# Handle foreign title pattern "'English title' AKA 'Foreign title'"
def splitEnglishForeignTitle(title):
    if FOREIGN_MOVIE_SPLITTER in title:
        return [part.strip() for part in title.split(FOREIGN_MOVIE_SPLITTER)]
    else:
        return [title]


def buildIMDBLink(imdbId):
    link = f"https://www.imdb.com/title/{imdbId}/"

    if isArgumentPresent(HYPERLINK_ARGUMENT_OFFSET, EXCEL_HYPERLINK):
        link = '=HYPERLINK("' + link + '")'

    return link


def langCodeToName(langCode):
    if langCode.lower() in LANG_PATCHES_TMDB:
        return LANG_PATCHES_TMDB[langCode]

    lang = pycountry.languages.get(alpha_2=langCode)
    return lang.name if lang else langCode.lower()


def langNameToCode(langName):
    for patchLangCode, patchLangName in LANG_PATCHES_TMDB.items():
        if patchLangName.lower() == langName.lower():
            return patchLangCode.lower()

    return pycountry.languages.lookup(langName).alpha_2


def findExactAlternativeTitle(localTitle, alterativeTitles):
    if not alterativeTitles:
        return None

    localTitle = localTitle.lower().strip()
    for t in alterativeTitles:
        if t["title"].lower().strip() == localTitle:
            return t

    return None


def findFuzzyAlternativeTitle(localTitle, alternativeTitles, threshold=THRESHOLD):
    if not alternativeTitles:
        return None

    localTitle = localTitle.lower().strip()
    bestMatch, bestScore = None, 0

    for t in alternativeTitles:
        score = SequenceMatcher(None, localTitle, t["title"].lower().strip()).ratio()
        if score > bestScore:
            bestMatch, bestScore = t, score

    # don't return early, since sequence matcher is highly inaccurate
    return bestMatch if bestScore >= threshold else None


class MatchStatus(Enum):
    VALID = auto()
    INVALID = auto()
    NO_MATCH = auto()


def validateTransliteratedTitleMatch(match):
    if not match:
        return MatchStatus.NO_MATCH, None

    altTitleType = match["type"].lower()
    if match["iso_3166_1"] == DEFAULT_COUNTRY and any(
        keyword in altTitleType for keyword in ALT_TITLE_TYPE_KEYWORDS_BLACKLIST
    ):
        return MatchStatus.INVALID, None

    return MatchStatus.VALID, match["title"]


def resolveRawTransliteratedTitle(localTransliteratedTitle, alternativeTitles):
    searchStrategies = [
        lambda: findExactAlternativeTitle(localTransliteratedTitle, alternativeTitles),
        lambda: findFuzzyAlternativeTitle(localTransliteratedTitle, alternativeTitles),
    ]

    for searchStrategy in searchStrategies:
        status, title = validateTransliteratedTitleMatch(searchStrategy())
        if status is MatchStatus.NO_MATCH:
            continue
        if status is MatchStatus.VALID:
            return title
        if status is MatchStatus.INVALID:
            # match found with default country, should be foreign
            return None

    return localTransliteratedTitle


def getLocalTransliteratedTitle(
    apiResult, titleVariant, titleVariants, threshold=THRESHOLD
):
    if not (rawTitle := apiResult.get("rawTitle")):
        return None
    isForeignTitle = (
        SequenceMatcher(
            None, titleVariant.lower().strip(), rawTitle.lower().strip()
        ).ratio()
        < threshold
    )
    isOneTitleOnly = 1 == len(titleVariants)
    isForeignMovie = apiResult.get("altTitles") or apiResult.get("originalTitle")
    isTransliteratedTitleOnly = isOneTitleOnly and isForeignTitle and isForeignMovie
    isDefaultLangTitleOnly = isOneTitleOnly and not isForeignTitle

    if isTransliteratedTitleOnly:
        return titleVariant

    if isDefaultLangTitleOnly:
        return None

    if isForeignTitle:
        return titleVariant

    return next((v for v in titleVariants if v != titleVariant), None)


def getMovieInfo(title, releaseYear, defaultLangCode):
    movieTitleVariants = splitEnglishForeignTitle(title)
    try:
        for titleVariant in movieTitleVariants:
            apiResult = tmdb.getMovieInfo(titleVariant, releaseYear, defaultLangCode)

            imdbId = apiResult.get("imdbId")
            if imdbId:
                # Convert IMDB id to Link
                apiResult["imdbId"] = buildIMDBLink(imdbId)
                apiResult["IMDB"] = apiResult.pop("imdbId")

                # Convert ISO 639-1 language code to full English name (fallback to code if unmapped)
                apiResult["langCode"] = langCodeToName(apiResult["langCode"])
                apiResult["lang"] = apiResult.pop("langCode")

                localTransliteratedTitle = getLocalTransliteratedTitle(
                    apiResult, titleVariant, movieTitleVariants
                )

                # if local title not similar to raw title then it must be transliterated/foreign
                # known errors that can occur from loose logic:
                # local title is not the same as raw title, but same language (different regional title used)
                # bad search result returns different movie with different title
                if localTransliteratedTitle:
                    # Convert originalTitle api value to a dummy entry in altTitles list
                    if apiResult.get("originalTitle"):
                        apiResult["altTitles"] = (apiResult.get("altTitles") or []) + [
                            {
                                "iso_3166_1": (
                                    originCountry[0]
                                    if (originCountry := apiResult["originCountry"])
                                    else ""
                                ),
                                "title": apiResult["originalTitle"],
                                "type": "original title",
                            }
                        ]

                    # Convert alternative titles list into a single transliterated title
                    apiResult["altTitles"] = resolveRawTransliteratedTitle(
                        localTransliteratedTitle, apiResult.get("altTitles")
                    )
                    apiResult["altTitle"] = apiResult.pop("altTitles")
                else:
                    apiResult["altTitle"] = None

                # cleanup apiResult
                apiResult.pop("altTitles", None)
                apiResult.pop("originalTitle", None)
                apiResult.pop("originCountry", None)

                return apiResult

    except tmdb.APIError as e:
        print(f"\n\n{e}\n")
        sys.exit(1)  # Do not continue, API has failed!

    # All searches returned None. Log error and continue to parse next movie.
    # **API knowledge gap, not for logging code or network errors.
    log_error(title, releaseYear)
    return {"rawTitle": None, "altTitle": None, "lang": None, "IMDB": None}


# Wrapper which prints progress for slow internet operations
# Check for user flag and modify output to work properly with excel
def getMovieInfoWrapper(title, releaseYear, defaultLangCode):
    global processedMovies, incompleteMovieCount
    if processedMovies == 0:
        printProgress(0)

    movieInfo = getMovieInfo(title, releaseYear, defaultLangCode)

    if not movieInfo.get("IMDB"):
        incompleteMovieCount += 1

    processedMovies += 1
    printProgress((processedMovies / movieCount) * 100)

    return movieInfo


def printProgress(progress):
    # with bar
    i = int(progress / 5)
    bar = " " + "[" + "=" * i + " " * (20 - i) + "]"
    sign = " %"
    progress = f"{progress:.1f}"[:-2] + " COMPLETE"
    print(f"{bar}{sign}{progress: >{12}}", end="\r")

    # no bar
    # print(f'{f"{progress:.1f}"[:-2]: >3}' + PROGRESS_STR, end="\r")


def printError(*errorMsg):
    print("".join(errorMsg))
    print(USAGE)
    sys.exit(1)


def dfToStringLJust(df, naRep="NaN", index=True):
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


def ptnFilterDebug(parsedMovies, debugOut):
    dfDebug = parsedMovies[["year", "title", "episodeName", "excess"]]
    debugOut = ConsoleDebug()
    debugTitle = "Tag Filter Screening:"
    debugPrompt = "Clear debug output and continue? [Y/N]:"

    if MATCH_TEXT_FILE_INDEX:
        dfDebug.index = dfDebug.index + 1

    if FILTER_PTN_DEBUG_OUTPUT:
        # Filter out known bad values. The displayed output will still have
        # known good values, so be careful when screening for bad values.
        dfDebug["episodeName"] = extractMovieTags(
            parsedMovies,
            "episodeName",
            useColNameAsTag=False,
            formatTags=False,
        )

        # Filter out whitelisted Excess tags here
        # Display str as single str and multi-str as list
        dfDebug["excess"] = extractExcessMovieTag(
            parsedMovies, formatted=False, returnLists=True, invert=True
        ).map(
            lambda tags: tags[0] if isinstance(tags, list) and len(tags) == 1 else tags
        )

    if UPPERCASE_CSV_HEADERS:
        dfDebug.columns = dfDebug.columns.str.upper()
        debugTitle = debugTitle.upper()
        debugPrompt = debugPrompt.upper()

    # print debugging info to help build PTN filtering rules
    debugStr = (
        dfToStringLJust(dfDebug, naRep=NA_REPLACEMENT_DEBUG_OUTPUT)
        if LEFT_JUSTIFY_DEBUG_OUTPUT
        else dfDebug.to_string(na_rep=NA_REPLACEMENT_DEBUG_OUTPUT)
    )
    debugOut.print(f"{debugTitle}\n\n" + debugStr)

    # prompt user to continue or exit. Long dfs cause the console to scroll
    # down. Auto scroll back up, so df rows can be screened from top to bottom.
    if debugOut.autoScrollThenAsk(f"\n{debugPrompt} "):
        debugOut.clear()
    else:
        sys.exit(0)


def deleteColumn(df, cols):
    if isinstance(cols, str):
        cols = [cols]

    return df.loc[:, ~df.columns.isin(cols)]


# when calling function use df[col].notna().any()
def extractMovieTags(parsedMovies, col, useColNameAsTag=True, formatTags=True):
    if useColNameAsTag:
        tagStr = TAG_AND_HEADER_LABELS[col]
        conditional = parsedMovies[col].fillna(False).astype(bool)
    else:  # useCellValueAsTag
        tagStr = parsedMovies[col].astype("string")
        conditional = (
            tagStr.notna()
            & tagStr.str.len().gt(1)
            & ~tagStr.isin(EPISODE_NAME_TAG_BLACKLIST)
        )

    if formatTags:
        return np.where(conditional, "[" + tagStr + "]", "")

    return np.where(conditional, tagStr, "")


def extractExcessMovieTag(
    parsedMovies, formatted=True, returnLists=False, invert=False
):
    # convert dictionary into lookup table
    lookupSeries = (
        pd.Series(EXCESS_TAG_WHITELIST, name="tags")
        .explode()
        .rename_axis("label")
        .reset_index()
    )

    excessSeries = parsedMovies["excess"].map(
        lambda x: [x] if isinstance(x, str) else x
    )

    # explode lists to allow vectorization
    values = excessSeries.explode().rename("tags").rename_axis("row").reset_index()

    # match excess tags with lookup table tags
    matches = values.merge(lookupSeries, on="tags")

    # count tags found for each label
    matched = matches.groupby(["row", "label"]).size().rename("found").reset_index()

    # make the 'lookupSeries required tag count' table
    required = lookupSeries.groupby("label").size().rename("required")

    # compare matched count with required tag count
    matched = matched.merge(required, on="label")
    matched = matched.loc[matched["found"].eq(matched["required"])]

    # return all non-whitelisted values. This is useful for debugging and
    # finding new tags to whitelist.
    if invert:
        # the filter reasons in labels but the output is in tags, so map the
        # satisfied (row, label) pairs back to their tags, then subtract those
        consumed = matches.merge(matched[["row", "label"]], on=["row", "label"])[
            ["row", "tags"]
        ].drop_duplicates()
        unmatched = values.merge(
            consumed, on=["row", "tags"], how="left", indicator=True
        )
        unmatched = unmatched.loc[
            unmatched["_merge"].eq("left_only")
            & unmatched["tags"].notna()
            & unmatched["tags"].str.len().gt(1)  # drop single-character values
        ]

        matched = unmatched.rename(columns={"tags": "label"})[["row", "label"]]

    # collect labels for each original row and restore original index
    if returnLists:
        labels = matched.groupby("row")["label"].agg(list)
        return labels.reindex(parsedMovies.index)

    if formatted:
        matched["label"] = "[" + matched["label"] + "]"
        labels = matched.groupby("row")["label"].sum()
    else:
        labels = matched.groupby("row")["label"].agg(" ".join)

    return labels.reindex(parsedMovies.index, fill_value="")


MINIMUM_ARGUMENT_COUNT = 2  # script name + text file input

# Arguments indexes
TEXT_FILE_ARGUMENT = 1
APPENDING = 2
HYPERLINK_STYLE = 3
DEBUGGING = 4

# Argument offsets, relative to the text file input argument
APPENDING_ARGUMENT_OFFSET = APPENDING - 1
HYPERLINK_ARGUMENT_OFFSET = HYPERLINK_STYLE - 1
DEBUGGING_ARGUMENT_OFFSET = DEBUGGING - 1

# Valid link style argument input
EXCEL_HYPERLINK = "excel"

# Argument descriptions - determines the order of arguments in the usage message
ARGUMENT_DESCRIPTORS = {
    "TF": "Text-file [(filename.txt)]: Torrent list text file being parsed into a CSV.",
    "A": "Appending [true, false, empty (default)]: Removes header from CSV.",
    "LS": "Hyperlink style [excel, empty (default)]: Solves hyperlink issues when importing CSV.",
    "D": "Debugging [true, false, empty (default)]: Enables debug output.",
}

# Script Manual
SCRIPT_NAME = Path(sys.argv[0]).name
USAGE = (
    "\n"
    + f"USAGE: {SCRIPT_NAME} "
    + " ".join(f"[-{a.lower()}]" for a in ARGUMENT_DESCRIPTORS)
    + "\n"
    + "\n".join(f"-{a.lower()}\t{d}" for a, d in ARGUMENT_DESCRIPTORS.items())
    + "\n"
)

# Valid Output
PROGRESS_STR = "% COMPLETED"
VALID_ARGUMENT = "SUCCESS: CSV results copied to your clipboard."
INCOMPLETE_DATA_WARNING = (
    "WARNING: {incompleteMovieCount} parsed movie{plural} couldn't be found "
    "online and failed to parse completely. See INCOMPLETE_MOVIES.txt."
)

# Invalid Output
INVALID_ARGUMENT = "INVALID ARGUMENT: "
FILE_NOT_FOUND = "No such file - "
INVALID_FILENAME = "Failed to parse filename. Expected a '.txt' file."

# Foreign movies
DEFAULT_LANGUAGE_CODE = langNameToCode(DEFAULT_LANGUAGE)

movieCount = 0  # number of movies parsed from file
processedMovies = 0  # number of movies finished processing
incompleteMovieCount = 0  # number of movies not found on TMDB

# valid argument(s)
if len(sys.argv) >= MINIMUM_ARGUMENT_COUNT and isTextFile(sys.argv[TEXT_FILE_ARGUMENT]):
    textFile = sys.argv[TEXT_FILE_ARGUMENT]  # IMDB database access

    # parse file and concatenate to a df
    parsedTextFile = pd.DataFrame()
    try:
        with open(textFile) as f:
            for line in f:
                df_dictionary = pd.DataFrame([PTN.parse(line)])
                parsedTextFile = pd.concat(
                    [parsedTextFile, df_dictionary], ignore_index=True
                )
    except IOError as e:
        printError(INVALID_ARGUMENT, FILE_NOT_FOUND, textFile)

    # truncate table to retrieve desired data
    # causes SettingWithCopyWarning if not copied and used as a view
    parsedMovies = parsedTextFile.reindex(
        columns=[
            "year",
            "title",
            "resolution",
            "quality",
            "unrated",
            "directorsCut",
            "excess",
            "extended",
            "episodeName",
        ]
    ).copy()
    movieCount = parsedMovies.shape[0]

    # print debugging info to help build PTN filtering rules
    if isArgumentPresent(DEBUGGING_ARGUMENT_OFFSET, "true"):
        ptnFilterDebug(parsedMovies, ConsoleDebug())

    # remap resolution and quality values (personal preference)
    parsedMovies["resolution"] = parsedMovies["resolution"].replace(
        {"2160p": "4K", "1080p": "", "720p": ""}
    )
    parsedMovies["quality"] = parsedMovies["quality"].replace(
        {"Blu-ray": "", "WEB-DL": "WEB", "WEBRip": "WEB"}
    )

    # remove NaN values before concatenation
    parsedMovies[["resolution", "quality"]] = parsedMovies[
        ["resolution", "quality"]
    ].fillna("")

    # combine resolution and quality into the quality column
    # https://stackoverflow.com/a/76428891
    parsedMovies["release"] = parsedMovies["resolution"] + " " + parsedMovies["quality"]
    parsedMovies = deleteColumn(parsedMovies, ["resolution", "quality"])

    # replace NaN values and clean up whitespace in df
    parsedMovies = parsedMovies.replace(r"^\s*$", np.nan, regex=True)
    parsedMovies = parsedMovies.apply(
        lambda x: x.map(lambda y: y.strip() if isinstance(y, str) else y)
    )

    # add additional movie info (Raw titles and IMDB links)
    # iterate through df https://stackoverflow.com/a/55557758
    movieInfo = [
        getMovieInfoWrapper(title, year, DEFAULT_LANGUAGE_CODE)
        for title, year in zip(parsedMovies["title"], parsedMovies["year"])
    ]
    dfMovieInfo = pd.DataFrame(movieInfo)

    # combine English title with transliterated title
    if COMBINE_DEFAULT_FOREIGN_TITLES:
        dfMovieInfo["rawTitle"] = np.where(
            dfMovieInfo["altTitle"].notna(),
            dfMovieInfo["altTitle"] + FOREIGN_MOVIE_SPLITTER + dfMovieInfo["rawTitle"],
            dfMovieInfo["rawTitle"],
        )
        dfMovieInfo = deleteColumn(dfMovieInfo, "altTitle")
    else:
        parsedMovies["foreign title"] = dfMovieInfo["altTitle"]
        dfMovieInfo = deleteColumn(dfMovieInfo, "altTitle")

    # add tags to raw title
    if ADD_TAGS_TO_TITLE:
        tags = np.full(len(parsedMovies), "", dtype=object)

        # create language tags
        foreignLangCol = "lang"
        foreignLanguageTags = np.where(
            dfMovieInfo[foreignLangCol].notna()
            & (dfMovieInfo[foreignLangCol].str.upper() != DEFAULT_LANGUAGE.upper()),
            "[" + dfMovieInfo[foreignLangCol] + "]",
            "",
        )

        tags += foreignLanguageTags

        dfMovieInfo = deleteColumn(dfMovieInfo, foreignLangCol)

        # create movie descriptor tags
        for boolTagCol in BOOL_TAG_COLS:
            if parsedMovies[boolTagCol].notna().any():
                tags += extractMovieTags(parsedMovies, boolTagCol)

        for strTagCol in STR_TAG_COLS:
            if parsedMovies[strTagCol].notna().any():
                tags += extractMovieTags(parsedMovies, strTagCol, useColNameAsTag=False)

        if parsedMovies[EXCESS_TAG_COLS[0]].notna().any():
            if COMBINE_RELEASE_AND_EXCESS_TAGS:
                excessTags = (
                    extractExcessMovieTag(
                        parsedMovies, formatted=FORMAT_EXCESS_TAGS_IN_RELEASE
                    )
                    .astype("string")
                    .str.upper()
                )

                hasExcessTags = excessTags.ne("")
                hasEmptyRelease = parsedMovies["release"].isna()

                parsedMovies.loc[hasExcessTags & hasEmptyRelease, "release"] = (
                    excessTags
                )
                parsedMovies.loc[hasExcessTags & ~hasEmptyRelease, "release"] += (
                    " " + excessTags
                )
            else:
                tags += extractExcessMovieTag(parsedMovies)

        parsedMovies = deleteColumn(
            parsedMovies, BOOL_TAG_COLS + STR_TAG_COLS + EXCESS_TAG_COLS
        )

        # final tag format changes
        formattedTags = pd.Series(tags, dtype="string")

        if ADD_SPACE_BETWEEN_TAGS:
            formattedTags = formattedTags.str.replace("][", "] [", regex=False)

        if UPPERCASE_TAGS:
            formattedTags = formattedTags.str.upper()

        # add tags to raw title
        dfMovieInfo["rawTitle"] += formattedTags.where(
            formattedTags.eq(""), " " + formattedTags
        )
    else:
        # filter lang col values
        dfMovieInfo["lang"] = dfMovieInfo["lang"].mask(
            dfMovieInfo["lang"].str.upper().eq(DEFAULT_LANGUAGE.upper())
        )

        # filter other version col values
        if parsedMovies[STR_TAG_COLS[0]].notna().any():
            parsedMovies[STR_TAG_COLS[0]] = extractMovieTags(
                parsedMovies, STR_TAG_COLS[0], useColNameAsTag=False, formatTags=False
            )

        # filter excess col values
        if parsedMovies[EXCESS_TAG_COLS[0]].notna().any():
            parsedMovies[EXCESS_TAG_COLS[0]] = extractExcessMovieTag(
                parsedMovies, returnLists=True
            )

        # add language col to main df
        parsedMovies["language"] = dfMovieInfo["lang"]
        dfMovieInfo = deleteColumn(dfMovieInfo, "lang")

    # overwrite title with rawTitle
    parsedMovies["title"] = dfMovieInfo["rawTitle"].fillna(parsedMovies["title"])
    dfMovieInfo = deleteColumn(dfMovieInfo, "rawTitle")

    # add IMDB column
    parsedMovies["IMDB"] = dfMovieInfo["IMDB"]
    dfMovieInfo = deleteColumn(dfMovieInfo, "IMDB")

    # set final order of output
    finalColumnOrder = ["year", "title", "release", "IMDB"]

    if not COMBINE_DEFAULT_FOREIGN_TITLES:
        finalColumnOrder.insert(finalColumnOrder.index("title") + 1, "foreign title")

    if not ADD_TAGS_TO_TITLE:
        # rename headers
        parsedMovies = parsedMovies.rename(
            columns={
                colName: label.lower()
                for colName, label in TAG_AND_HEADER_LABELS.items()
            }
        )

        # insert language col
        finalColumnOrder.insert(finalColumnOrder.index("release"), "language")

        # insert movie cut cols
        movieCutCols = [label.lower() for label in TAG_AND_HEADER_LABELS.values()]

        finalColumnOrder[
            finalColumnOrder.index("release") : finalColumnOrder.index("release")
        ] = movieCutCols

    parsedMovies = parsedMovies[finalColumnOrder]

    # convert df to CSV
    # if appending data no headers needed
    if isArgumentPresent(APPENDING_ARGUMENT_OFFSET, "true"):
        csv = parsedMovies.to_csv(header=False, index=False)
    elif UPPERCASE_CSV_HEADERS:
        csv = parsedMovies.rename(columns=str.upper).to_csv(header=True, index=False)
    else:
        csv = parsedMovies.to_csv(header=True, index=False)

    # output newline to avoid overwriting progress bar
    print()

    # warn if any movies were not found by the TMDB API
    if incompleteMovieCount > 0:
        print(
            INCOMPLETE_DATA_WARNING.format(
                incompleteMovieCount=incompleteMovieCount,
                plural="" if incompleteMovieCount == 1 else "s",
            )
        )

    pyperclip.copy(csv)  # copy to clipboard
    print(VALID_ARGUMENT)
else:  # invalid argument(s)
    printError(INVALID_ARGUMENT, INVALID_FILENAME)
