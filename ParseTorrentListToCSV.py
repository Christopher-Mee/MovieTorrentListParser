# Christopher Mee
# 2023-08-16
# Parse and convert a list of p2p movie file names into CSV format
import re  # Regex
import sys  # System
from difflib import SequenceMatcher  # Str compare/search tool
from enum import Enum, auto  # Ternary return solution

import numpy as np  # Numpy
import pandas as pd  # Pandas (dataframes)
import PTN  # parse-torrent-title
import pycountry  # Movie languages
import pyperclip  # Pyperclip

import tmdbClient as tmdb  # TMDB API

# SETTINGS #####################################
# CSV Headers
UPPERCASE_CSV_HEADERS = True

# Movie title
COMBINE_DEFAULT_FOREIGN_TITLES = True

# Tags
ADD_TAGS_TO_TITLE = True
COMBINE_RELEASE_AND_EXCESS_TAGS = True
FORMAT_EXCESS_TAGS_IN_RELEASE = True
UPPERCASE_TAGS = True
ADD_SPACE_BETWEEN_TAGS = True

# English Foreign combined title splitter
FOREIGN_MOVIE_SPLITTER = " AKA "

# Language to ignore when tagging movie titles
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


def extractExcessMovieTag(parsedMovies, formatted=True, returnLists=False):
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


MINIMUM_ARGUMENT_COUNT = 2

# Arguments
TEXT_FILE_ARGUMENT = 1
APPENDING = 2
HYPERLINK_STYLE = 3

# Argument offsets
APPENDING_ARGUMENT_OFFSET = 1
HYPERLINK_ARGUMENT_OFFSET = 2

# Valid argument input
EXCEL_HYPERLINK = "excel"

# Argument descriptors
TF = "-tf\t\tText-file filename (.txt)"
A = "-a\t\tAppending [true, false, empty (default)]: Removes header from CSV."
LS = "-ls\t\tHyperlink style [excel, empty (default)]: Solves hyperlink issues when importing CSV."

# Script Manual
USAGE = "USAGE: ParseTorrentListToCSV.py [-tf] [-ls] [-a]\n" + TF + "\n" + A + "\n" + LS

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
INVALID_FILENAME = "Cannot parse filename"

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
