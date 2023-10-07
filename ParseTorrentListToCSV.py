# Christopher Mee
# 2023-08-16
# Parse and convert a list of p2p movie file names into CSV format
import sys  # System
import re  # Regex
import PTN  # parse-torrent-title
import pandas as pd  # Pandas (dataframes)
import numpy as np  # Numpy
from imdb import Cinemagoer  # Cinemagoer
import pyperclip  # Pyperclip


def isTextFile(str):
    pattern = "^.*\.txt$"
    return re.search(pattern, str)


def getIMDBLink(IMDB, title, year):
    results = IMDB.search_movie(title + " " + str(year))
    movie = results[0]
    return IMDB.get_imdbURL(movie)


# Wrapper which prints progress for slow internet operations
def getIMDBLinkWrapper(IMDB, title, year):
    global processedMovies
    if processedMovies == 0:
        printProgress(0)

    link = getIMDBLink(IMDB, title, year)

    processedMovies += 1
    printProgress((processedMovies / movieCount) * 100)

    return link


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


VALID_ARGUMENT_COUNT = 2
TEXT_FILE_ARGUMENT = 1
USAGE = "USAGE: ParseTorrentListToCSV.py [-tf]\n-tf\t\tText-file filename (.txt)"
VALID_ARGUMENT = "SUCCESS: CSV results copied to your clipboard."
PROGRESS_STR = "% COMPLETED"
INVALID_ARGUMENT = "INVALID ARGUMENT: "
FILE_NOT_FOUND = "No such file - "
INVALID_FILENAME = "Cannot parse filename"

movieCount = 0  # number of movies parsed from file
processedMovies = 0  # number of movies finished processing

# valid argument(s)
if len(sys.argv) == VALID_ARGUMENT_COUNT and isTextFile(sys.argv[TEXT_FILE_ARGUMENT]):
    textFile = sys.argv[TEXT_FILE_ARGUMENT]
    IMDB = Cinemagoer()  # IMDB database access

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
    parsedMovies = parsedTextFile[["year", "title", "resolution", "quality"]].copy()
    movieCount = parsedMovies.shape[0]

    # remap resolution and quality values (personal preference)
    parsedMovies["resolution"] = parsedMovies["resolution"].replace(
        {"2160p": "4K", "1080p": "", "720p": ""}
    )
    parsedMovies["quality"] = parsedMovies["quality"].replace(
        {"Blu-ray": "", "WEB-DL": "WEB", "WEBRip": "WEB"}
    )

    # remove NaN values before concatonation
    parsedMovies[["resolution", "quality"]] = parsedMovies[
        ["resolution", "quality"]
    ].fillna("")

    # combine resolution and quality into the quality column
    # https://stackoverflow.com/a/76428891
    parsedMovies["quality"] = parsedMovies["resolution"] + " " + parsedMovies["quality"]
    parsedMovies = parsedMovies.loc[:, parsedMovies.columns != "resolution"]

    # replace NaN values and clean up whitespace in df
    parsedMovies = parsedMovies.replace(r"^\s*$", np.nan, regex=True)
    parsedMovies.columns = parsedMovies.columns.str.strip()

    # get IMDB links
    # iterate through df https://stackoverflow.com/a/55557758
    IMDB_links = [
        getIMDBLinkWrapper(IMDB, title, year)
        for title, year in zip(parsedMovies["title"], parsedMovies["year"])
    ]
    IMDB_links = pd.DataFrame(IMDB_links, columns=["IMDB"])  # name column

    parsedMovies = pd.concat(
        [parsedMovies, IMDB_links], axis=1
    )  # append IMDB_links to movies

    csv = parsedMovies.to_csv(index=False)  # convert df to CSV

    pyperclip.copy(csv)  # copy to clipboard
    print("\n" + VALID_ARGUMENT)
else:  # invalid argument(s)
    printError(INVALID_ARGUMENT, INVALID_FILENAME)
