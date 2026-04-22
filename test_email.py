from dotenv import load_dotenv
load_dotenv()

from app.services.email_service import EmailService

result = EmailService().send_email(
    to="brkomanapalli@gmail.com",
    subject="Test from AI Paperwork Assistant",
    html="<h1>Email is working!</h1><p>Your deadline reminders will be sent to this address.</p>",
    text="Email is working! Your deadline reminders will be sent to this address.",
)
print("Sent:", result)