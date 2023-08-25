from flask import Flask, render_template_string
from email.message import EmailMessage
from email.headerregistry import Address
from smtplib import SMTP_SSL

import firebase_admin
from firebase_admin import firestore
import markdown2


fb_app = firebase_admin.initialize_app()
db = firestore.client()


app = Flask(__name__)


def send_email(subject, unit, send_test, code):
    smtp_config = db.collection('configs').document('smtp').get().to_dict()

    with SMTP_SSL(smtp_config.get('hostname'), port=smtp_config.get('port')) as smtp:
        smtp.login(smtp_config.get('username'), smtp_config.get('password'))

        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = Address(smtp_config.get(
            'from_display_name'), addr_spec=smtp_config.get('from_email'))
        if send_test:
            msg['To'] = Address(smtp_config.get(
                'from_display_name'), addr_spec=smtp_config.get('from_email'))
        else:
            msg['To'] = [c.get('email')
                         for c in get_contacts_from_unit(unit)]
        cc = [Address(smtp_config.get(
            'from_display_name'), addr_spec=smtp_config.get('from_email'))]
        if not send_test:
            cc = cc + smtp_config.get('always_cc', [])
        msg['Cc'] = cc
        msg.set_content(code)
        msg.add_alternative(markdown2.markdown(
            render_template_string(code, unit=unit)), subtype='html')
        smtp.send_message(msg)


@app.cli.command("send-email")
def send_email_cmd():
    smtp_config = db.collection('configs').document('smtp').get().to_dict()

    count = 0
    for mail in db.collection('mailqueue').stream():
        mail_dict = mail.to_dict()
        send_email(subject=mail_dict.get('subject'), unit=mail_dict.get(
            'unit'), send_test=mail_dict.get('send_test'), code=mail_dict.get('code'))

        mail.reference.delete()
        count = count + 1
        if count > smtp_config.get('emails_per_loop'):
            break
