from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, List

from markdown import markdown

import site
from fpdf import FPDF

from open_webui.env import STATIC_DIR, FONTS_DIR
from open_webui.models.chats import ChatTitleMessagesForm


class PDFGenerator:
    """
    Description:
    The `PDFGenerator` class is designed to create PDF documents from chat messages.
    The process involves transforming markdown content into HTML and then into a PDF format

    Attributes:
    - `form_data`: An instance of `ChatTitleMessagesForm` containing title and messages.

    """

    def __init__(self, form_data: ChatTitleMessagesForm):
        self.html_body = None
        self.messages_html = None
        self.form_data = form_data

        self.css = Path(STATIC_DIR / "assets" / "pdf-style.css").read_text()

    def format_timestamp(self, timestamp: float) -> str:
        """Convert a UNIX timestamp to a formatted date string."""
        try:
            date_time = datetime.fromtimestamp(timestamp)
            return date_time.strftime("%Y-%m-%d, %H:%M:%S")
        except (ValueError, TypeError) as e:
            # Log the error if necessary
            return ""

    def _build_html_message(self, message: Dict[str, Any]) -> str:
        """
        Builds an HTML representation of a single chat message.
        
        Parameters:
            message (Dict[str, Any]): A dictionary containing message details.
                Expected keys:
                - 'role' (str, optional): Message sender's role. Defaults to 'user'.
                - 'content' (str, optional): Message text content. Defaults to empty string.
                - 'timestamp' (float, optional): Message timestamp.
                - 'model' (str, optional): AI model name for assistant messages.
        
        Returns:
            str: HTML-formatted message with role, model, timestamp, and content.
        
        Notes:
            - Converts role to title case (e.g., 'user' → 'User')
            - Displays model name only for assistant messages
            - Formats timestamp using `format_timestamp` method
            - Preserves raw content without markdown conversion
        """
        role = message.get("role", "user")
        content = message.get("content", "")
        timestamp = message.get("timestamp")

        model = message.get("model") if role == "assistant" else ""

        date_str = self.format_timestamp(timestamp) if timestamp else ""

        # extends pymdownx extension to convert markdown to html.
        # - https://facelessuser.github.io/pymdown-extensions/usage_notes/
        # html_content = markdown(content, extensions=["pymdownx.extra"])

        html_message = f"""
            <div>
                <div>
                    <h4>
                        <strong>{role.title()}</strong>
                        <span style="font-size: 12px;">{model}</span>
                    </h4>
                    <div> {date_str} </div>
                </div>
                <br/>
                <br/>

                <div>
                    {content}
                </div>
            </div>
            <br/>
          """
        return html_message

    def _generate_html_body(self) -> str:
        """
        Generates the complete HTML structure for the PDF document.
        
        This method creates an HTML document with a responsive viewport, incorporating the chat title and pre-generated HTML messages. The HTML is structured with nested div elements and includes the title as an h2 heading.
        
        Returns:
            str: A fully formed HTML document string containing the chat title and messages, ready for PDF conversion.
        """
        return f"""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            </head>
            <body>
            <div>
                <div>
                    <h2>{self.form_data.title}</h2>
                    {self.messages_html}
                </div>
            </div>
            </body>
        </html>
        """

    def generate_chat_pdf(self) -> bytes:
        """
        Generate a PDF document from chat messages with comprehensive font and internationalization support.
        
        This method creates a PDF file from a collection of chat messages, handling various font requirements and supporting multiple languages. It dynamically locates font directories, adds necessary font files, and generates a PDF with HTML-formatted chat messages.
        
        Parameters:
            None (uses instance attributes)
        
        Returns:
            bytes: A byte representation of the generated PDF document
        
        Raises:
            Exception: If any error occurs during PDF generation process
        
        Notes:
            - Supports multiple font families: NotoSans, NotoSansKR, NotoSansJP, NotoSansSC, Twemoji
            - Handles different installation scenarios (pip install, editable install)
            - Automatically sets page breaks and font configurations
            - Converts chat messages to HTML before PDF rendering
        """
        try:
            global FONTS_DIR

            pdf = FPDF()
            pdf.add_page()

            # When running using `pip install` the static directory is in the site packages.
            if not FONTS_DIR.exists():
                FONTS_DIR = Path(site.getsitepackages()[0]) / "static/fonts"
            # When running using `pip install -e .` the static directory is in the site packages.
            # This path only works if `open-webui serve` is run from the root of this project.
            if not FONTS_DIR.exists():
                FONTS_DIR = Path("./backend/static/fonts")

            pdf.add_font("NotoSans", "", f"{FONTS_DIR}/NotoSans-Regular.ttf")
            pdf.add_font("NotoSans", "b", f"{FONTS_DIR}/NotoSans-Bold.ttf")
            pdf.add_font("NotoSans", "i", f"{FONTS_DIR}/NotoSans-Italic.ttf")
            pdf.add_font("NotoSansKR", "", f"{FONTS_DIR}/NotoSansKR-Regular.ttf")
            pdf.add_font("NotoSansJP", "", f"{FONTS_DIR}/NotoSansJP-Regular.ttf")
            pdf.add_font("NotoSansSC", "", f"{FONTS_DIR}/NotoSansSC-Regular.ttf")
            pdf.add_font("Twemoji", "", f"{FONTS_DIR}/Twemoji.ttf")

            pdf.set_font("NotoSans", size=12)
            pdf.set_fallback_fonts(
                ["NotoSansKR", "NotoSansJP", "NotoSansSC", "Twemoji"]
            )

            pdf.set_auto_page_break(auto=True, margin=15)

            # Build HTML messages
            messages_html_list: List[str] = [
                self._build_html_message(msg) for msg in self.form_data.messages
            ]
            self.messages_html = "<div>" + "".join(messages_html_list) + "</div>"

            # Generate full HTML body
            self.html_body = self._generate_html_body()

            pdf.write_html(self.html_body)

            # Save the pdf with name .pdf
            pdf_bytes = pdf.output()

            return bytes(pdf_bytes)
        except Exception as e:
            raise e
