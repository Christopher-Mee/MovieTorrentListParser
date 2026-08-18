# Christopher Mee
# 2023-08-16
# Parse and convert a list of p2p movie file names into CSV format
import re  # Regex
import sys  # System
from difflib import SequenceMatcher  # Str compare/search tool

import numpy as np  # Numpy
import pandas as pd  # Pandas (dataframes)
import PTN  # parse-torrent-title
import pycountry  # Movie languages
import pyperclip  # Pyperclip

import tmdbClient as tmdb  # TMDB API

# SETTINGS #####################################
# English Foreign combined title splitter
FOREIGN_MOVIE_SPLITTER = " AKA "

# Language to ignore when tagging movie titles
DEFAULT_LANGUAGE = "English"

# TMDb Language code manual patches
LANG_PATCHES_TMDB = {"cn": "Cantonese"}

# Title similarity threshold
THRESHOLD = 0.78
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
    localTitle = localTitle.lower().strip()
    for t in alterativeTitles:
        if t["title"].lower().strip() == localTitle:
            return t["title"]
    return None


def findFuzzyAlternativeTitle(localTitle, alternativeTitles, threshold=THRESHOLD):
    localTitle = localTitle.lower().strip()
    bestMatch, bestScore = None, 0
    for t in alternativeTitles:
        score = SequenceMatcher(None, localTitle, t["title"].lower().strip()).ratio()
        if score > bestScore:
            bestMatch, bestScore = t["title"], score

    # don't return early, since sequence matcher is highly inaccurate
    return bestMatch if bestScore >= threshold else None


def resolveRawTransliteratedTitle(localTransliteratedTitle, alternativeTitles):
    match = findExactAlternativeTitle(localTransliteratedTitle, alternativeTitles)
    if match:
        return match

    match = findFuzzyAlternativeTitle(
        localTransliteratedTitle, alternativeTitles, threshold=0.8
    )
    if match:
        return match

    return localTransliteratedTitle


def getLocalTransliteratedTitle(
    apiResult, titleVariant, titleVariants, threshold=THRESHOLD
):
    # if one element only, title was not split
    if len(titleVariants) == 1:
        return None

    rawTitle = apiResult.get("rawTitle")
    if not rawTitle:
        return None

    isForeignTitle = (
        SequenceMatcher(
            None, titleVariant.lower().strip(), rawTitle.lower().strip()
        ).ratio()
        < threshold
    )

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

                # Convert originalTitle api value to a dummy entry in altTitles list
                if apiResult.get("originalTitle"):
                    apiResult["altTitles"] = (apiResult.get("altTitles") or []) + [
                        {"title": apiResult["originalTitle"]}
                    ]
                apiResult.pop("originalTitle", None)

                # Convert alternative titles list into a single transliterated title
                localTransliteratedTitle = getLocalTransliteratedTitle(
                    apiResult, titleVariant, movieTitleVariants
                )
                if localTransliteratedTitle:
                    apiResult["altTitles"] = resolveRawTransliteratedTitle(
                        localTransliteratedTitle, apiResult.get("altTitles")
                    )
                    apiResult["altTitle"] = apiResult.pop("altTitles")
                else:
                    apiResult["altTitle"] = None

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
    if (
        "resolution" not in parsedTextFile.columns
        and "quality" not in parsedTextFile.columns
    ):
        parsedTextFile["resolution"] = np.nan
        parsedTextFile["quality"] = np.nan
    elif "resolution" not in parsedTextFile.columns:
        parsedTextFile["resolution"] = np.nan
    elif "quality" not in parsedTextFile.columns:
        parsedTextFile["quality"] = np.nan

    parsedMovies = parsedTextFile[["year", "title", "resolution", "quality"]].copy()
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
    parsedMovies["quality"] = parsedMovies["resolution"] + " " + parsedMovies["quality"]
    parsedMovies = parsedMovies.loc[:, parsedMovies.columns != "resolution"]

    # replace NaN values and clean up whitespace in df
    parsedMovies = parsedMovies.replace(r"^\s*$", np.nan, regex=True)
    parsedMovies = parsedMovies.apply(
        lambda x: x.str.strip() if x.dtype == "object" else x
    )

    # add additional movie info (Raw titles and IMDB links)
    # iterate through df https://stackoverflow.com/a/55557758
    movieInfo = [
        getMovieInfoWrapper(title, year, DEFAULT_LANGUAGE_CODE)
        for title, year in zip(parsedMovies["title"], parsedMovies["year"])
    ]
    dfMovieInfo = pd.DataFrame(movieInfo)

    # combine English title with transliterated title
    dfMovieInfo["rawTitle"] = np.where(
        dfMovieInfo["altTitle"].notna(),
        dfMovieInfo["altTitle"] + FOREIGN_MOVIE_SPLITTER + dfMovieInfo["rawTitle"],
        dfMovieInfo["rawTitle"],
    )

    # tag title with foreign language
    dfMovieInfo["rawTitle"] = np.where(
        dfMovieInfo["lang"].str.upper() != DEFAULT_LANGUAGE.upper(),
        dfMovieInfo["rawTitle"] + " [" + dfMovieInfo["lang"].str.upper() + "]",
        dfMovieInfo["rawTitle"],
    )

    # delete lang column
    dfMovieInfo = dfMovieInfo.loc[:, dfMovieInfo.columns != "lang"]

    # overwrite title with rawTitle (including embedded tags)
    parsedMovies["title"] = dfMovieInfo["rawTitle"].fillna(parsedMovies["title"])

    # add IMDB column
    parsedMovies["IMDB"] = dfMovieInfo["IMDB"]

    # convert df to CSV
    if isArgumentPresent(APPENDING_ARGUMENT_OFFSET, "true"):
        csv = parsedMovies.to_csv(header=False, index=False)
    else:
        csv = parsedMovies.to_csv(header=True, index=False)

    # Output newline to avoid overwriting progress bar
    print()

    # Warn if any movies were not found by the TMDB API
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
