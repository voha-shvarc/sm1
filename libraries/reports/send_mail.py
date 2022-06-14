import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_mail(creds, receivers, mail_content):
    sender_address = creds["name"]
    sender_pass = creds["App Password"]
    receiver_address = receivers

    message = MIMEMultipart()
    message["From"] = sender_address
    message["To"] = receiver_address
    message["Subject"] = "A test mail sent by Python. It has an attachment."

    message.attach(MIMEText(mail_content, "text/html"))

    session = smtplib.SMTP("smtp.gmail.com", 587)
    session.starttls()
    session.login(sender_address, sender_pass)
    text = message.as_string()
    session.sendmail(sender_address, receiver_address, text)
    session.quit()
    print("Mail Sent")
