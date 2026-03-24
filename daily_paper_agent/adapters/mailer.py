from __future__ import annotations

import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def send_report_mail(mail_cfg: dict, pdf_path: Path | None) -> None:
    if not mail_cfg.get("enabled", False):
        return

    to_addrs = mail_cfg.get("to_addrs", [])
    if not to_addrs:
        raise ValueError("mail.to_addrs is empty")

    sender = mail_cfg.get("from_addr") or mail_cfg.get("username")
    if not sender:
        raise ValueError("mail.from_addr or mail.username is required")

    msg = MIMEMultipart()
    msg["Subject"] = mail_cfg.get("subject_prefix", "[DailyPaperAgent]")
    msg["From"] = sender
    msg["To"] = ", ".join(to_addrs)

    msg.attach(MIMEText(mail_cfg.get("intro_message", "今天你读论文了嘛？"), _subtype="plain", _charset="utf-8"))

    if bool(mail_cfg.get("attach_pdf", True)) and pdf_path and pdf_path.exists():
        part = MIMEBase("application", "pdf")
        part.set_payload(pdf_path.read_bytes())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{pdf_path.name}"')
        msg.attach(part)

    host = mail_cfg.get("smtp_host", "smtp.gmail.com")
    port = int(mail_cfg.get("smtp_port", 587))
    use_ssl = bool(mail_cfg.get("use_ssl", False))
    use_tls = bool(mail_cfg.get("use_tls", True))
    username = mail_cfg.get("username", "")
    password = mail_cfg.get("password", "")

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=30) as s:
            if username:
                s.login(username, password)
            s.sendmail(sender, to_addrs, msg.as_string())
        return

    with smtplib.SMTP(host, port, timeout=30) as s:
        if use_tls:
            s.starttls()
        if username:
            s.login(username, password)
        s.sendmail(sender, to_addrs, msg.as_string())
