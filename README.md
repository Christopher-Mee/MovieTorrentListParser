# MovieTorrentListParser

Install script

select an install location  
clone repo  
python -m venv venv  
pip install -r requirements.txt --use-pep517

Usage

python ParseTorrentListToCSV.py 'list.txt'

CSV Output

Year, Title, Resolution/Quality, IMDB link

Known issues

4K is not parsed, leaving resolution field empty. (Forked dependency has some regressions in output, reverting back to original will fix issue)
