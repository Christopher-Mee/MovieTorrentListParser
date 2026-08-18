# Christopher Mee
# 2026-07-05
# Replace Cinemagoer with 'TMDB' a dedicated movie API
# https://developer.themoviedb.org/reference/getting-started
# https://developer.themoviedb.org/docs/errors
# Why? - Cinemagoer now wants the user to run a local DB that
# takes an hour to build each time IMDB is updated
import os

import requests  # API calls
from dotenv import load_dotenv  # API key retrieval
from requests.adapters import HTTPAdapter  # Error handling
from urllib3.util.retry import Retry  # Error handling

from apiRateLimiter import RateLimiter, rateLimited  # Rate limit API calls


class APIError(Exception):
    pass


load_dotenv()  # reads .env into environment variables

# HTTP STATUS CODES
OK = 200

# TMDB 'SEARCH' API DICTIONARY KEYS
RESULT_LIST = "results"
TMDB_ID = "id"

# TMDB 'EXTERNAL ID'S' API DICTIONARY KEYS
IMDB_ID = "imdb_id"

# CALL TYPES/ERROR DESCRIPTORS
MOVIE_SEARCH = "movie search results"
EXTERNAL_IDS = "movies' external IDs"
ALTERNATIVE_TITLES = "movies' alternative titles"

# FINAL VARIABLES
BASE_URL = "https://api.themoviedb.org/3"
TMDB_ACCESS_TOKEN = os.getenv("TMDB_ACCESS_TOKEN")
MAX_CALLS_PER_SECOND = 40

# SESSION SETUP
headers = {"Authorization": f"Bearer {TMDB_ACCESS_TOKEN}", "accept": "application/json"}
rateLimiter = RateLimiter(MAX_CALLS_PER_SECOND)

session = (  # Set up session once, instead of calling request each time
    requests.session()
)
retries = Retry(  # Retry if rate limit fails or another error occurs
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    respect_retry_after_header=True,
)
session.mount("https://", HTTPAdapter(max_retries=retries))
session.headers.update(headers)


# Generic API error handler
def handleApiErrors(callType, response):
    raise APIError(
        f"ERROR: Failed to retrieve {callType} — HTTP {response.status_code}: {response.reason}"
    )


# API call to search for a movie, using title and release year.
# https://developer.themoviedb.org/reference/search-movie
@rateLimited(rateLimiter)
def searchMovie(title, releaseYear, forceYearFallback=False):
    url = f"{BASE_URL}/search/movie"
    params = {
        "query": title,
        "include_adult": "false",
        "language": "en-US",
        "page": 1,
    }

    if not forceYearFallback:
        params["primary_release_year"] = releaseYear
    else:
        params["year"] = releaseYear

    movieSearchResults = None
    usedYearFallback = forceYearFallback
    Done = False
    while not Done:
        response = session.get(url, params=params)

        if OK == response.status_code:
            movieSearchResults = response.json()
        else:
            handleApiErrors(MOVIE_SEARCH, response)

        if (  # Year fallback search
            movieSearchResults != None  # results not None
            and not movieSearchResults[RESULT_LIST]  # results not empty
            and not usedYearFallback  # Loop exit
        ):
            params.pop("primary_release_year")
            params["year"] = releaseYear
            usedYearFallback = True
        else:
            Done = True

    return movieSearchResults


# API call to get the external IDs for a 'TMDB' movie ID.
# https://developer.themoviedb.org/reference/movie-external-ids
@rateLimited(rateLimiter)
def getExternalIDs(internalID):
    url = f"{BASE_URL}/movie/{internalID}/external_ids"
    response = session.get(url)

    if OK == response.status_code:
        movieExternalIDs = response.json()
        return movieExternalIDs
    else:
        handleApiErrors(EXTERNAL_IDS, response)


@rateLimited(rateLimiter)
def getAlternativeTitles(internalID):
    url = f"{BASE_URL}/movie/{internalID}/alternative_titles"
    response = session.get(url)

    if OK == response.status_code:
        alternativeTitles = response.json()
        return alternativeTitles
    else:
        handleApiErrors(ALTERNATIVE_TITLES, response)


# Search and return pulled movie info from the 'The Movie Data Base'.
# Returns the following info from the FIRST search result ONLY:
# 1) Movie title w/ special characters included
# 2) 'IMDB' ID
# 'None' for all fields, if NO search results are found, or the 'IMDB' ID is unknown.
def getMovieInfo(title, releaseYear, defaultLangCode):
    rawTitle = originalTitle = alternativeTitles = langCode = imdbId = None
    Done = forceYearFallback = False
    while not Done:
        movieSearchResults = searchMovie(
            title, releaseYear, forceYearFallback=forceYearFallback
        )

        firstResult = next(
            iter((movieSearchResults or {}).get(RESULT_LIST) or []), None
        )
        if not firstResult:
            Done = True
            continue

        internalId = firstResult.get(TMDB_ID)
        externalIds = getExternalIDs(internalId)
        if not externalIds:
            Done = True
            continue

        imdbId = externalIds.get(IMDB_ID)
        if (  # Bad search fix (API returned a movie not listed on IMDB)
            not imdbId and not forceYearFallback
        ):
            forceYearFallback = True
            continue

        rawTitle = firstResult.get("title")
        langCode = firstResult.get("original_language")

        isForeignMovie = defaultLangCode != langCode
        if isForeignMovie and (alternativeTitles := getAlternativeTitles(internalId)):
            alternativeTitles = alternativeTitles.get("titles")
            originalTitle = firstResult["original_title"]

        Done = True

    return {
        "rawTitle": rawTitle,
        "originalTitle": originalTitle,
        "altTitles": alternativeTitles,
        "langCode": langCode,
        "imdbId": imdbId,
    }


# Example Year Fallback (Fix for TMDB search error): # "The Blue Rose" 2023
# Example Language Tag: "Love Letter" 1995
