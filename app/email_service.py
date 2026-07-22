"""Invio delle notifiche email per assenze e sostituzioni registrate.

L'invio avviene in un thread separato e non deve mai bloccare né far
fallire l'operazione principale (creare un'assenza o una sostituzione):
qualunque errore SMTP viene solo registrato nei log, mai propagato."""

import logging
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app import email_config
from app.templates import templates

logger = logging.getLogger("calendario_turni.email")


def _invia_ora(oggetto: str, corpo_html: str, destinatari: list[str] | None = None) -> bool:
    """destinatari=None usa DESTINATARI_NOTIFICHE (le notifiche di assenze/
    sostituzioni): il riepilogo giornaliero (app/riepilogo_giornaliero.py)
    passa invece i suoi destinatari specifici. Restituisce True solo se
    l'invio è riuscito, per chi ha bisogno di saperlo (es. il pulsante
    manuale "Invia ora"); il fire-and-forget delle notifiche normali ignora
    il valore di ritorno."""
    destinatari = destinatari if destinatari is not None else email_config.DESTINATARI_NOTIFICHE
    messaggio = MIMEMultipart("alternative")
    messaggio["Subject"] = oggetto
    messaggio["From"] = email_config.SMTP_MITTENTE or email_config.SMTP_UTENTE
    messaggio["To"] = ", ".join(destinatari)
    messaggio.attach(MIMEText(corpo_html, "html", "utf-8"))

    try:
        classe_smtp = smtplib.SMTP_SSL if email_config.SMTP_USA_SSL else smtplib.SMTP
        with classe_smtp(
            email_config.SMTP_HOST,
            email_config.SMTP_PORTA,
            timeout=email_config.SMTP_TIMEOUT_SECONDI,
        ) as server:
            if not email_config.SMTP_USA_SSL:
                server.starttls()
            server.login(email_config.SMTP_UTENTE, email_config.SMTP_PASSWORD)
            server.sendmail(
                email_config.SMTP_MITTENTE or email_config.SMTP_UTENTE,
                destinatari,
                messaggio.as_string(),
            )
        return True
    except Exception:
        # Non deve mai interrompere l'operazione che ha generato la
        # notifica: nel peggiore dei casi l'email non parte, ma
        # l'assenza/sostituzione restano comunque registrate correttamente.
        logger.exception("Invio notifica email fallito (oggetto=%r)", oggetto)
        return False


def invia_notifica_asincrona(oggetto: str, template_nome: str, contesto: dict) -> None:
    """Non fa nulla se le notifiche non sono configurate (vedi
    app/email_config.py): il chiamante non deve preoccuparsi di controllarlo
    prima di invocare questa funzione."""
    if not email_config.notifiche_configurate():
        return
    corpo_html = templates.env.get_template(template_nome).render(**contesto)
    threading.Thread(target=_invia_ora, args=(oggetto, corpo_html), daemon=True).start()
