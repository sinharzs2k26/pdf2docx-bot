import os
import logging
import tempfile
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pdf2docx import Converter
import asyncio
from io import BytesIO
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 *PDF to DOCX Converter Bot*\n\n"
        "Send me a PDF file and I'll convert it to DOCX format!\n\n"
        "Commands:\n"
        "/start - Show this message\n"
        "/help - Get help\n\n"
        "Just send any PDF file to get started!",
        parse_mode="Markdown"
    )

# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *How to use:*\n\n"
        "1. Send me a PDF file\n"
        "2. Wait for conversion\n"
        "3. Download the converted DOCX file\n\n"
        "⚠️ *Limitations:*\n"
        "- File size limit: 20MB\n"
        "- Only PDF files are accepted\n"
        "- Conversion may take a few seconds\n\n"
        "If you have any issues, make sure your PDF is not password protected.",
        parse_mode="Markdown"
    )

# Convert PDF to DOCX
def convert_pdf_to_docx(pdf_bytes: bytes) -> bytes:
    """Convert PDF bytes to DOCX bytes"""
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as pdf_temp:
        pdf_temp.write(pdf_bytes)
        pdf_path = pdf_temp.name
    
    docx_path = pdf_path.replace('.pdf', '.docx')
    
    try:
        cv = Converter(pdf_path)
        cv.convert(docx_path, start=0, end=None)
        cv.close()
        
        with open(docx_path, 'rb') as docx_file:
            docx_bytes = docx_file.read()
            
    finally:
        # Clean up temp files
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
        if os.path.exists(docx_path):
            os.unlink(docx_path)
    
    return docx_bytes

# Handle PDF files
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Get the file
        file = await update.message.document.get_file()
        
        # Check if it's a PDF
        if not update.message.document.file_name.lower().endswith('.pdf'):
            await update.message.reply_text("❌ Please send a PDF file!")
            return
        
        # Check file size (20MB limit for Telegram, we'll use 19MB for safety)
        if update.message.document.file_size > 19 * 1024 * 1024:
            await update.message.reply_text("❌ File is too large! Please send a PDF under 20MB.")
            return
        
        # Send processing message
        processing_msg = await update.message.reply_text("🔄 Processing your PDF file...")
        
        # Download PDF
        pdf_bytes = await file.download_as_bytearray()
        
        # Convert to DOCX
        await processing_msg.edit_text("⚡ Converting PDF to DOCX...")
        
        # Run conversion in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        docx_bytes = await loop.run_in_executor(None, convert_pdf_to_docx, bytes(pdf_bytes))
        
        await processing_msg.edit_text("✅ Conversion complete! Sending DOCX file...")
        
        # Send DOCX file
        docx_io = BytesIO(docx_bytes)
        docx_io.name = update.message.document.file_name.replace('.pdf', '.docx').replace('.PDF', '.docx')
        
        await update.message.reply_document(
            document=docx_io,
            caption=f"✅ Converted: {update.message.document.file_name} → {docx_io.name}"
        )
        
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error converting PDF: {e}")
        await update.message.reply_text(
            f"❌ Error converting PDF: {str(e)}\n\n"
            "Please ensure:\n"
            "1. File is a valid PDF\n"
            "2. PDF is not password protected\n"
            "3. File size is under 20MB"
        )

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("❌ An error occurred. Please try again.")

# Main function
def main():
    # Create Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    application.add_handler(MessageHandler(filters.Document.ALL, 
        lambda u, c: u.message.reply_text("❌ Please send a PDF file!")))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Create health server
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is alive!')
        
        def log_message(self, format, *args):
            pass  # Silence logs

    def run_health_server():
        port = int(os.environ.get("PORT", 10000))
        httpd = HTTPServer(('0.0.0.0', port), HealthHandler)
        logger.info(f"✅ Health server on port {port}")
        httpd.serve_forever()
    
    # Start health server
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    # Start the bot
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
       )
       
if __name__ == "__main__":
    main()