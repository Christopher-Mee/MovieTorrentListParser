# MovieTorrentListParser

### Install script ###

select an install location  
clone repo  
python -m venv venv  
python -m pip install --upgrade pip  
pip install -r requirements.txt --use-pep517

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
When the wrong IMDB link is selected, it cannot be found easily, since the movie title is NOT overwritten with the IMDB version.  
~~Need to have atleast one movie with a resolution and source (Web, Blu-Ray).~~  
~~White space is not properly removed.~~
