# Simhub-Racenet-Server
Get EA WRC 23 Learderboard and Club data from Racenet.com. Then show in-game with SimHub Overlay.

1. get your refresh token from racenet.com
<img src="images/get_refresh_token.png" width="40%" height="40%">  

2. launch server by `python server.py` in terminal.

3. paste your refresh token to the terminal.

4. Open this Overlay in Simhub Dashboard Editor, in `Dashboard variables`:
    a. change the `clubName` to the club you want. 
    b. enter the path to the server.py in the global variable `server_path`.
    c. save and close the editor.