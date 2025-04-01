from typing import Dict, Optional, List
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from pydantic import EmailStr
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

class EmailService:
    def __init__(self):
        """
        Initialize the EmailService instance.
        
        Configures the Brevo API client using the API key from the BREVO_API_KEY environment variable and 
        sets up a Jinja2 environment for rendering email templates from the 'templates/email' directory.
        """
        self.configuration = sib_api_v3_sdk.Configuration()
        self.configuration.api_key['api-key'] = os.getenv('BREVO_API_KEY')
        self.api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(self.configuration))
        
        # Initialize Jinja2 environment
        template_dir = Path(__file__).parent.parent / 'templates' / 'email'
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))
    
    def send_welcome_mail(self, to_email: EmailStr, username: str, password: str) -> bool:
        """
        Send a welcome email to a newly registered user.
        
        This method renders the welcome email template using the provided username and 
        password, sets a default subject and sender address, and sends the email via the 
        Brevo API. It returns True if the email is sent successfully, or False if an error occurs.
        
        Args:
            to_email: The recipient's email address.
            username: The recipient's name.
            password: The user's temporary or initial password.
        
        Returns:
            bool: True if the email was sent successfully, False otherwise.
        """
        try:
            subject = "Willkommen bei Bchat!"
            sender = {"name": "Bchat", "email": os.getenv('SENDER_EMAIL', 'noreply@beyondtheloop.ai')}
            to = [{"email": to_email, "name": username}]
            
            # Load and render the template
            template = self.jinja_env.get_template('welcome.html')
            html_content = template.render(
                name=username,
                password=password
            )
            
            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=to,
                html_content=html_content,
                sender=sender,
                subject=subject
            )
            
            self.api_instance.send_transac_email(send_smtp_email)
            return True
            
        except ApiException as e:
            print(f"Exception when sending registration email: {e}")
            return False


    def send_custom_email(self, to_email: EmailStr, subject: str, html_content: str, 
                         recipient_name: Optional[str] = None) -> bool:
        """
                         Send a custom email using the Sendinblue API.
                         
                         Constructs and sends an email with the specified subject and HTML content. If a recipient name
                         is provided, it is used; otherwise, the recipient's email is used as the name. Returns True if the
                         email is sent successfully, or False if an exception occurs.
                         """
        try:
            sender = {"name": "Beyond The Loop", "email": os.getenv('SENDER_EMAIL', 'noreply@beyondtheloop.com')}
            to = [{"email": to_email, "name": recipient_name or to_email}]
            
            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=to,
                html_content=html_content,
                sender=sender,
                subject=subject
            )
            
            self.api_instance.send_transac_email(send_smtp_email)
            return True
            
        except ApiException as e:
            print(f"Exception when sending custom email: {e}")
            return False

    def send_budget_mail_80(self, to_email: EmailStr, recipient_name: Optional[str] = None) -> bool:
        """
        Sends a warning email when budget usage reaches 80% of the limit.
        
        Renders the email content using the 'budget-mail-80.html' template and sends it via the Brevo API.
        The email is configured with a predefined subject and sender information, and the recipient’s display name
        defaults to the email address if not provided. Returns True if the email is sent successfully, or False
        if an API exception occurs.
        """
        try:
            subject = "Abrechnungslimit fast erreicht"
            sender = {"name": "Beyond The Loop", "email": os.getenv('SENDER_EMAIL', 'noreply@beyondtheloop.ai')}
            to = [{"email": to_email, "name": recipient_name or to_email}]
            
            # Load and render the template
            template = self.jinja_env.get_template('budget-mail-80.html')
            html_content = template.render()
            
            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=to,
                html_content=html_content,
                sender=sender,
                subject=subject
            )
            
            self.api_instance.send_transac_email(send_smtp_email)
            return True
            
        except ApiException as e:
            print(f"Exception when sending budget warning (80%) email: {e}")
            return False

    def send_budget_mail_100(self, to_email: EmailStr, recipient_name: Optional[str] = None) -> bool:
        """
        Sends a critical warning email when budget reaches 100% of its limit.
        
        This method constructs and sends an email using a predefined Jinja2 template to alert the
        recipient that the budget has fully been consumed. The email includes the configured sender
        information and uses the provided recipient email and name (if given). It returns True if the
        email is sent successfully, and False if an ApiException is encountered.
        """
        try:
            subject = "Achtung: Abrechnungslimit erreicht!"
            sender = {"name": "Beyond The Loop", "email": os.getenv('SENDER_EMAIL', 'noreply@beyondtheloop.ai')}
            to = [{"email": to_email, "name": recipient_name or to_email}]
            
            # Load and render the template
            template = self.jinja_env.get_template('budget-mail-100.html')
            html_content = template.render()
            
            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=to,
                html_content=html_content,
                sender=sender,
                subject=subject
            )
            
            self.api_instance.send_transac_email(send_smtp_email)
            return True
            
        except ApiException as e:
            print(f"Exception when sending budget warning (100%) email: {e}")
            return False
