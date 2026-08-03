"""Versione del programma, mostrata in Stato del programma (/stato).

Va tenuta allineata a installer.iss e a versione_client.txt /
versione_server.txt, che sono le informazioni incorporate negli eseguibili.
Non è un doppione lasciato lì per distrazione: quei tre file non sono
importabili da Python (li leggono Inno Setup e PyInstaller), e qui serve un
valore che il programma possa mostrare a chi lo usa. Il disallineamento è
impedito da tests/test_versione.py, che li confronta.
"""

VERSIONE = "1.1.4"
