# MovieTorrentListParser

### Install script ###

select an install location  
clone repo   
python -m venv venv  
python -m pip install --upgrade pip  
pip install -r requirements.txt --use-pep517


### TMDb setup ###
Create a free TMDb account (if you don't have one): [https://www.themoviedb.org/signup](https://www.themoviedb.org/signup)  
Log in, then go to your API settings: [https://www.themoviedb.org/settings/api](https://www.themoviedb.org/settings/api)  
Click `Create` to request API access (choose `Developer` if prompted for use type).  
Copy your `API Read Access Token` (the long token starting with "eyJ..."), not the shorter `API Key`.  
Inside the `.env` file, replace `your_read_access_token_here` with your TMDb `API Read Access Token`.  


### Usage ###

ParseTorrentListToCSV.py -tf, -a, -ls  
python ParseTorrentListToCSV.py 'list.txt'

### Example usage ### 
* You want to use a input file named - input.txt
* Then use the output and append it to an existing csv with pre-existing headers
* and your csv is an excel sheet which needs special formatting to properly hyperlink
  
python ParseTorrentListToCSV input.txt True Excel

### CSV Output ###

Year, Title, Resolution/Quality, IMDB link

### Known Issues ###  

'8-bit Christmas' movie title is not parsed correctly.  
~~When the wrong IMDB link is selected, it cannot be found easily, since the movie title is NOT overwritten with the IMDB version.~~  
~~Need to have at least one movie with a resolution and source (Web, Blu-Ray).~~  
~~White space is not properly removed.~~
