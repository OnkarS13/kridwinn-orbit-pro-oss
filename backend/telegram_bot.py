"""
Telegram Bot Backend
Handles all Telegram bot commands for license management
"""

import os
import sys
import logging
import html
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pages.licensing.firebase_client import get_firebase_client
from pages.licensing.license_generator import create_license_data
from pages.licensing.credentials import generate_credentials
from pages.licensing.secure_loader import load_firebase_credentials_data

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Firebase client
firebase = None

# Bot configuration from environment variables (secure for VM deployment)
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MASTER_ADMIN_ID_STR = os.getenv('TELEGRAM_MASTER_ADMIN_ID')

# Firebase credentials path from environment variable (required for VM deployment)
FIREBASE_CREDENTIALS_PATH = os.getenv('FIREBASE_CREDENTIALS_PATH')

# Validate critical environment variables (required for production)
if not BOT_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN environment variable is required!")
    logger.error("   Set it in .env file or as environment variable before running the bot.")
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

if not MASTER_ADMIN_ID_STR:
    logger.error("❌ TELEGRAM_MASTER_ADMIN_ID environment variable is required!")
    logger.error("   Set it in .env file or as environment variable before running the bot.")
    raise ValueError("TELEGRAM_MASTER_ADMIN_ID environment variable is required")

try:
    MASTER_ADMIN_ID = int(MASTER_ADMIN_ID_STR)
except ValueError:
    logger.error(f"❌ Invalid TELEGRAM_MASTER_ADMIN_ID: {MASTER_ADMIN_ID_STR} (must be a number)")
    raise ValueError(f"TELEGRAM_MASTER_ADMIN_ID must be a valid integer, got: {MASTER_ADMIN_ID_STR}")

logger.info("✅ Bot configuration loaded from environment variables")


def init_firebase():
    """Initialize Firebase client"""
    global firebase
    if firebase is None:
        # Priority 1: Use environment variable path (for VM deployment)
        if FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH):
            firebase = get_firebase_client(credentials_path=FIREBASE_CREDENTIALS_PATH)
            logger.info(f"Firebase initialized from environment path: {FIREBASE_CREDENTIALS_PATH}")
        else:
            # Priority 2: Try to load encrypted Firebase credentials using secure_loader (for local dev)
            try:
                firebase_creds_data = load_firebase_credentials_data()
                firebase = get_firebase_client(credentials_data=firebase_creds_data)
                logger.info("Firebase initialized from encrypted credentials")
            except FileNotFoundError:
                # Priority 3: Try default secure_config location
                default_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'secure_config', 'firebase_creds.enc')
                if os.path.exists(default_path):
                    try:
                        firebase_creds_data = load_firebase_credentials_data()
                        firebase = get_firebase_client(credentials_data=firebase_creds_data)
                        logger.info("Firebase initialized from default encrypted credentials location")
                    except Exception as e:
                        logger.error(f"Failed to load default encrypted credentials: {e}")
                        raise ValueError("Firebase credentials not available")
                else:
                    logger.error(
                        "Firebase credentials not found. Options:\n"
                        "1. Set FIREBASE_CREDENTIALS_PATH environment variable pointing to firebase_admin.json\n"
                        "2. Ensure encrypted firebase_creds.enc exists in secure_config/"
                    )
                    raise ValueError("Firebase credentials not available")


def is_master_admin(user_id: int) -> bool:
    """Check if user is master admin"""
    return user_id == MASTER_ADMIN_ID


def is_assistant(user_id: int) -> bool:
    """Check if user is an assistant"""
    assistant = firebase.get_assistant_by_telegram(user_id)
    return assistant is not None and assistant.get('is_active', False)


def get_user_role(user_id: int) -> str:
    """Get user role (master/assistant/none)"""
    if is_master_admin(user_id):
        return "master"
    elif is_assistant(user_id):
        return "assistant"
    return "none"


# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "master":
        message = "🔐 <b>Kridwinn Orbit Pro - Master Admin</b>\n\n" \
                 "Welcome! You have full system access.\n\n" \
                 "Use /help to see all available commands."
    elif role == "assistant":
        assistant = firebase.get_assistant_by_telegram(user_id)
        message = f"🔐 <b>Welcome, {assistant['name']}!</b>\n\n" \
                 f"Role: Assistant\n\n" \
                 "Use /help to see your available commands."
    else:
        message = "⚠️ You are not authorized to use this bot."
    
    await update.message.reply_text(message, parse_mode='HTML')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    if role == "master":
        message = """📚 <b>MASTER ADMIN COMMANDS</b>

<b>License Management:</b>
/create_license &lt;name&gt; &lt;email&gt; &lt;days&gt;
  → Generates license + username + password
/list_licenses - View all licenses
/status &lt;license_key&gt; - Check license status
/revoke &lt;license_key&gt; [reason] - Revoke license
/unrevoke &lt;license_key&gt; - Restore revoked license
/extend &lt;license_key&gt; &lt;days&gt; - Extend trial (adds days)
/set_expiry &lt;license_key&gt; &lt;days&gt; - Set expiry to X days from now (replaces)

<b>Assistant Management:</b>
/add_assistant &lt;telegram_id&gt; &lt;name&gt; &lt;email&gt;
/list_assistants - View all assistants
/remove_assistant &lt;assistant_id&gt;
/toggle_assistant &lt;assistant_id&gt; - Enable/disable

<b>Monitoring:</b>
/logs &lt;machine_id&gt; [count] - View machine logs
/tamper_logs - View tamper attempts
/search_user &lt;email_or_name&gt; - Search licenses
/active_machines - List active machines
/expired_machines - List expired machines
/blocked_machines - List blocked machines

<b>Statistics:</b>
/stats - System statistics

<b>Bulk Operations:</b>
/bulk_extend &lt;assistant_id&gt; &lt;days&gt; - Extend all licenses
/bulk_revoke &lt;assistant_id&gt; - Revoke all licenses
/export_data &lt;assistant_id&gt; - Export as JSON

<b>Examples:</b>
/create_license John john@email.com 7
/search_user john@email.com
/bulk_extend asst_123456 14"""
    else:  # assistant
        message = """📚 <b>ASSISTANT COMMANDS</b>

<b>License Management:</b>
/create_license &lt;name&gt; &lt;email&gt; &lt;days&gt;
/my_licenses - View your licenses
/status &lt;license_key&gt; - Check license status
/revoke &lt;license_key&gt; [reason] - Revoke license
/unrevoke &lt;license_key&gt; - Restore revoked license
/extend &lt;license_key&gt; &lt;days&gt; - Extend trial (adds days)
/set_expiry &lt;license_key&gt; &lt;days&gt; - Set expiry to X days from now (replaces)

<b>Monitoring:</b>
/logs &lt;machine_id&gt; [count] - View machine logs
/search_user &lt;email_or_name&gt; - Search your licenses
/active_machines - Your active machines
/expired_machines - Your expired machines
/blocked_machines - Your blocked machines

<b>Statistics:</b>
/my_stats - Your statistics

<b>Examples:</b>
/create_license John john@email.com 7
/search_user john@email.com"""
    
    await update.message.reply_text(message, parse_mode='HTML')


async def create_license(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /create_license command"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: /create_license <name> <email> <days>\n"
            "Example: /create_license John john@email.com 7"
        )
        return
    
    try:
        name = context.args[0]
        email = context.args[1]
        days = int(context.args[2])
        
        # Get creator info
        if role == "master":
            created_by = "master_001"
        else:
            assistant = firebase.get_assistant_by_telegram(user_id)
            created_by = assistant['assistant_id']
        
        # Generate credentials
        username, password, password_hash = generate_credentials(name)
        
        # Create license
        license_data = create_license_data(
            user_name=name,
            user_email=email,
            trial_days=days,
            created_by=created_by,
            created_by_role=role
        )
        
        # Add credentials to license data
        license_data['username'] = username
        license_data['password'] = password  # Store plain password (encrypted in transit by Firebase)
        license_data['password_hash'] = password_hash  # Also keep hash for future use
        
        # Save to Firebase
        success = firebase.create_license(license_data)
        
        if success:
            key = license_data['license_key']
            # Escape special characters in username and password to prevent HTML parsing errors
            escaped_username = html.escape(username)
            escaped_password = html.escape(password)
            message = f"✅ <b>LICENSE CREATED</b>\n\n" \
                     f"<b>License Key:</b>\n<code>{key}</code>\n\n" \
                     f"<b>Login Credentials:</b>\n" \
                     f"Username: <code>{escaped_username}</code>\n" \
                     f"Password: <code>{escaped_password}</code>\n\n" \
                     f"User: {html.escape(name)}\n" \
                     f"Email: {html.escape(email)}\n" \
                     f"Trial: {days} days\n\n" \
                     f"⚠️ <b>IMPORTANT:</b> Save these credentials securely!\n" \
                     f"The password cannot be recovered."
            
            await update.message.reply_text(message, parse_mode='HTML')
        else:
            await update.message.reply_text("❌ Failed to create license.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def list_licenses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list_licenses command"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role != "master":
        await update.message.reply_text("⚠️ Master admin only.")
        return
    
    licenses = firebase.get_all_licenses()
    
    if not licenses:
        await update.message.reply_text("No licenses found.")
        return
    
    message = f"📋 <b>ALL LICENSES ({len(licenses)})</b>\n\n"
    
    for lic in licenses[:10]:  # Show first 10
        key = lic['license_key']
        status = lic.get('status', 'unknown')
        user = lic.get('user_info', {}).get('name', 'N/A')
        message += f"<code>{key}</code>\n{user} - {status}\n\n"
    
    if len(licenses) > 10:
        message += f"... and {len(licenses) - 10} more"
    
    await update.message.reply_text(message, parse_mode='HTML')


async def my_licenses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /my_licenses command"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role != "assistant":
        await update.message.reply_text("⚠️ Assistant only.")
        return
    
    assistant = firebase.get_assistant_by_telegram(user_id)
    licenses = firebase.get_licenses_by_creator(assistant['assistant_id'])
    
    if not licenses:
        await update.message.reply_text("No licenses found.")
        return
    
    message = f"📋 <b>YOUR LICENSES ({len(licenses)})</b>\n\n"
    
    for lic in licenses[:10]:
        key = lic['license_key']
        status = lic.get('status', 'unknown')
        user = lic.get('user_info', {}).get('name', 'N/A')
        message += f"<code>{key}</code>\n{user} - {status}\n\n"
    
    await update.message.reply_text(message, parse_mode='HTML')


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /status <license_key>")
        return
    
    license_key = context.args[0]
    license_data = firebase.get_license(license_key)
    
    if not license_data:
        await update.message.reply_text("❌ License not found.")
        return
    
    # Assistants can only view status of their own licenses
    if role == "assistant":
        assistant = firebase.get_assistant_by_telegram(user_id)
        if not assistant or license_data.get('created_by') != assistant['assistant_id']:
            await update.message.reply_text("⚠️ You can only view status of your own licenses.")
            return
    
    user_info = license_data.get('user_info', {})
    machine_id = license_data.get('machine_id', 'Not activated')
    status_val = license_data.get('status', 'unknown')
    expires_at = license_data.get('expires_at', 'N/A')
    is_blocked = license_data.get('is_blocked', False)
    
    message = f"📊 <b>LICENSE STATUS</b>\n\n" \
             f"<code>{license_key}</code>\n\n" \
             f"User: {user_info.get('name', 'N/A')}\n" \
             f"Email: {user_info.get('email', 'N/A')}\n" \
             f"Machine: <code>{machine_id}</code>\n" \
             f"Status: {status_val}\n" \
             f"Blocked: {'Yes' if is_blocked else 'No'}\n" \
             f"Expires: {expires_at[:10] if expires_at != 'N/A' else 'N/A'}"
    
    await update.message.reply_text(message, parse_mode='HTML')


async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /revoke command"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /revoke <license_key> [reason]")
        return
    
    license_key = context.args[0]
    license_data = firebase.get_license(license_key)
    
    if not license_data:
        await update.message.reply_text("❌ License not found.")
        return
    
    # Assistants can only revoke their own licenses
    if role == "assistant":
        assistant = firebase.get_assistant_by_telegram(user_id)
        if not assistant or license_data.get('created_by') != assistant['assistant_id']:
            await update.message.reply_text("⚠️ You can only revoke your own licenses.")
            return
    
    reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "Revoked by admin"
    
    success = firebase.revoke_license(license_key, reason)
    
    if success:
        await update.message.reply_text(f"✅ License revoked: <code>{license_key}</code>", parse_mode='HTML')
    else:
        await update.message.reply_text("❌ Failed to revoke license.")


async def unrevoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unrevoke command"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /unrevoke <license_key>")
        return
    
    license_key = context.args[0]
    license_data = firebase.get_license(license_key)
    
    if not license_data:
        await update.message.reply_text("❌ License not found.")
        return
    
    # Assistants can only unrevoke their own licenses
    if role == "assistant":
        assistant = firebase.get_assistant_by_telegram(user_id)
        if not assistant or license_data.get('created_by') != assistant['assistant_id']:
            await update.message.reply_text("⚠️ You can only restore your own licenses.")
            return
    
    if not license_data.get('is_blocked'):
        await update.message.reply_text("ℹ️ License is not revoked.")
        return
    
    success = firebase.restore_license(license_key)
    
    if success:
        user_info = license_data.get('user_info', {})
        message = f"♻️ <b>LICENSE RESTORED</b>\n\n" \
                 f"License: <code>{license_key}</code>\n" \
                 f"User: {user_info.get('name', 'N/A')}\n" \
                 f"Status: Active"
        await update.message.reply_text(message, parse_mode='HTML')
    else:
        await update.message.reply_text("❌ Failed to restore license.")


async def extend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /extend command"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /extend <license_key> <days>")
        return
    
    license_key = context.args[0]
    license_data = firebase.get_license(license_key)
    
    if not license_data:
        await update.message.reply_text("❌ License not found.")
        return
    
    # Assistants can only extend their own licenses
    if role == "assistant":
        assistant = firebase.get_assistant_by_telegram(user_id)
        if not assistant or license_data.get('created_by') != assistant['assistant_id']:
            await update.message.reply_text("⚠️ You can only extend your own licenses.")
            return
    
    try:
        days = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid number of days.")
        return
    
    success = firebase.extend_license(license_key, days)
    
    if success:
        await update.message.reply_text(f"✅ License extended by {days} days: <code>{license_key}</code>", parse_mode='HTML')
    else:
        await update.message.reply_text("❌ Failed to extend license.")


async def set_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /set_expiry command - Set license expiry to exactly X days from now"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /set_expiry <license_key> <days>\n\nSets expiry to exactly X days from now (replaces current expiry).")
        return
    
    license_key = context.args[0]
    license_data = firebase.get_license(license_key)
    
    if not license_data:
        await update.message.reply_text("❌ License not found.")
        return
    
    # Assistants can only set expiry for their own licenses
    if role == "assistant":
        assistant = firebase.get_assistant_by_telegram(user_id)
        if not assistant or license_data.get('created_by') != assistant['assistant_id']:
            await update.message.reply_text("⚠️ You can only modify your own licenses.")
            return
    
    try:
        days = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid number of days.")
        return
    
    success = firebase.set_license_expiry(license_key, days)
    
    if success:
        await update.message.reply_text(
            f"✅ License expiry set to {days} days from now: <code>{license_key}</code>\n\n"
            f"⚠️ Note: This replaces the current expiry date (does not add days).",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text("❌ Failed to set license expiry.")


async def add_assistant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add_assistant command"""
    user_id = update.effective_user.id
    
    if not is_master_admin(user_id):
        await update.message.reply_text("⚠️ Master admin only.")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: /add_assistant <telegram_id> <name> <email>\n"
            "Example: /add_assistant 123456789 Jane jane@email.com"
        )
        return
    
    try:
        telegram_id = int(context.args[0])
        name = context.args[1]
        email = context.args[2]
        
        # Generate assistant ID
        assistant_id = f"asst_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Create assistant data
        assistant_data = {
            'assistant_id': assistant_id,
            'telegram_id': telegram_id,
            'name': name,
            'email': email,
            'role': 'assistant',
            'created_by': 'master_001',
            'created_at': datetime.now().isoformat(),
            'is_active': True,
            'permissions': [
                'create_license',
                'revoke_license',
                'extend_license',
                'view_own_licenses'
            ]
        }
        
        # Save to Firebase
        success = firebase.create_assistant(assistant_data)
        
        if success:
            message = f"✅ <b>ASSISTANT ADDED</b>\n\n" \
                     f"ID: <code>{assistant_id}</code>\n" \
                     f"Name: {name}\n" \
                     f"Email: {email}\n" \
                     f"Telegram ID: {telegram_id}\n" \
                     f"Status: Active"
            await update.message.reply_text(message, parse_mode='HTML')
        else:
            await update.message.reply_text("❌ Failed to add assistant.")
            
    except ValueError:
        await update.message.reply_text("❌ Invalid Telegram ID (must be a number).")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def list_assistants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list_assistants command"""
    user_id = update.effective_user.id
    
    if not is_master_admin(user_id):
        await update.message.reply_text("⚠️ Master admin only.")
        return
    
    assistants = firebase.get_all_assistants()
    
    if not assistants:
        await update.message.reply_text("No assistants found.")
        return
    
    message = f"👥 <b>ALL ASSISTANTS ({len(assistants)})</b>\n\n"
    
    for asst in assistants:
        assistant_id = asst.get('assistant_id')
        name = asst.get('name', 'N/A')
        email = asst.get('email', 'N/A')
        telegram_id = asst.get('telegram_id', 'N/A')
        is_active = asst.get('is_active', False)
        status = "✅ Active" if is_active else "❌ Inactive"
        
        message += f"<b>{name}</b>\n" \
                  f"ID: <code>{assistant_id}</code>\n" \
                  f"Email: {email}\n" \
                  f"Telegram: {telegram_id}\n" \
                  f"Status: {status}\n\n"
    
    await update.message.reply_text(message, parse_mode='HTML')


async def remove_assistant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remove_assistant command"""
    user_id = update.effective_user.id
    
    if not is_master_admin(user_id):
        await update.message.reply_text("⚠️ Master admin only.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /remove_assistant <assistant_id>")
        return
    
    assistant_id = context.args[0]
    
    # Check if assistant exists
    assistant = firebase.get_assistant(assistant_id)
    if not assistant:
        await update.message.reply_text(f"❌ Assistant not found: {assistant_id}")
        return
    
    # Delete assistant
    success = firebase.delete_assistant(assistant_id)
    
    if success:
        message = f"✅ <b>ASSISTANT REMOVED</b>\n\n" \
                 f"ID: <code>{assistant_id}</code>\n" \
                 f"Name: {assistant.get('name', 'N/A')}"
        await update.message.reply_text(message, parse_mode='HTML')
    else:
        await update.message.reply_text("❌ Failed to remove assistant.")


async def toggle_assistant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /toggle_assistant command"""
    user_id = update.effective_user.id
    
    if not is_master_admin(user_id):
        await update.message.reply_text("⚠️ Master admin only.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /toggle_assistant <assistant_id>")
        return
    
    assistant_id = context.args[0]
    
    # Get current assistant data
    assistant = firebase.get_assistant(assistant_id)
    if not assistant:
        await update.message.reply_text(f"❌ Assistant not found: {assistant_id}")
        return
    
    # Toggle active status
    current_status = assistant.get('is_active', False)
    new_status = not current_status
    
    success = firebase.update_assistant(assistant_id, {'is_active': new_status})
    
    if success:
        status_text = "enabled" if new_status else "disabled"
        message = f"✅ <b>ASSISTANT {status_text.upper()}</b>\n\n" \
                 f"ID: <code>{assistant_id}</code>\n" \
                 f"Name: {assistant.get('name', 'N/A')}\n" \
                 f"Status: {'Active' if new_status else 'Inactive'}"
        await update.message.reply_text(message, parse_mode='HTML')
    else:
        await update.message.reply_text("❌ Failed to toggle assistant.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    user_id = update.effective_user.id
    
    if not is_master_admin(user_id):
        await update.message.reply_text("⚠️ Master admin only.")
        return
    
    licenses = firebase.get_all_licenses()
    assistants = firebase.get_all_assistants()
    
    total = len(licenses)
    active = sum(1 for l in licenses if l.get('status') == 'active')
    pending = sum(1 for l in licenses if l.get('status') == 'pending')
    revoked = sum(1 for l in licenses if l.get('is_blocked'))
    
    active_assistants = sum(1 for a in assistants if a.get('is_active', False))
    
    message = f"📊 <b>SYSTEM STATISTICS</b>\n\n" \
             f"<b>Licenses:</b>\n" \
             f"Total: {total}\n" \
             f"Active: {active}\n" \
             f"Pending: {pending}\n" \
             f"Revoked: {revoked}\n\n" \
             f"<b>Assistants:</b>\n" \
             f"Active: {active_assistants}"
    
    await update.message.reply_text(message, parse_mode='HTML')


async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /my_stats command"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    # Get creator ID
    if role == "master":
        creator_id = "master_001"
    else:
        assistant = firebase.get_assistant_by_telegram(user_id)
        creator_id = assistant['assistant_id']
    
    # Get licenses by creator
    licenses = firebase.get_licenses_by_creator(creator_id)
    
    total = len(licenses)
    active = sum(1 for l in licenses if l.get('status') == 'active')
    pending = sum(1 for l in licenses if l.get('status') == 'pending')
    revoked = sum(1 for l in licenses if l.get('is_blocked'))
    
    message = f"📊 <b>YOUR STATISTICS</b>\n\n" \
             f"Total Licenses: {total}\n" \
             f"Active: {active}\n" \
             f"Pending: {pending}\n" \
             f"Revoked: {revoked}"
    
    await update.message.reply_text(message, parse_mode='HTML')


# ==================== MONITORING COMMANDS ====================

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /logs command - View machine activity logs"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "Usage: /logs <machine_id> [count]\n"
            "Example: /logs A1B2C3D4E5F6G7H8 10"
        )
        return
    
    machine_id = context.args[0]
    count = int(context.args[1]) if len(context.args) > 1 else 10
    
    try:
        # Assistants can only view logs for machines belonging to their licenses
        if role == "assistant":
            # Get license by machine_id to check ownership
            license_data = firebase.get_license_by_machine(machine_id)
            if not license_data:
                await update.message.reply_text(f"❌ No license found for machine: {machine_id}")
                return
            
            assistant = firebase.get_assistant_by_telegram(user_id)
            if not assistant or license_data.get('created_by') != assistant['assistant_id']:
                await update.message.reply_text("⚠️ You can only view logs for your own licenses' machines.")
                return
        
        # Get logs from Firebase
        logs_list = firebase.get_machine_logs(machine_id, limit=count)
        
        if not logs_list:
            await update.message.reply_text(f"No logs found for machine: {machine_id}")
            return
        
        message = f"📋 <b>MACHINE LOGS</b>\n\n"
        message += f"Machine ID: <code>{machine_id}</code>\n"
        message += f"Showing last {len(logs_list)} events:\n\n"
        
        for log in logs_list:
            event_type = log.get('event_type', 'unknown')
            timestamp = log.get('timestamp', 'N/A')
            status = log.get('status', 'N/A')
            
            # Format timestamp
            if hasattr(timestamp, 'strftime'):
                timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            else:
                timestamp_str = str(timestamp)[:19] if timestamp != 'N/A' else 'N/A'
            
            message += f"• {event_type} - {status}\n"
            message += f"  {timestamp_str}\n\n"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def tamper_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tamper_logs command - View tamper attempts"""
    user_id = update.effective_user.id
    
    if not is_master_admin(user_id):
        await update.message.reply_text("⚠️ Master admin only.")
        return
    
    try:
        # Get tamper attempts from Firebase
        attempts = firebase.get_tamper_attempts(limit=20)
        
        if not attempts:
            await update.message.reply_text("✅ No tamper attempts detected!")
            return
        
        message = f"⚠️ <b>TAMPER ATTEMPTS ({len(attempts)})</b>\n\n"
        
        for attempt in attempts:
            machine_id = attempt.get('machine_id', 'N/A')
            tamper_type = attempt.get('tamper_type', 'unknown')
            timestamp = attempt.get('timestamp', 'N/A')
            details = attempt.get('details', 'N/A')
            
            # Format timestamp
            if hasattr(timestamp, 'strftime'):
                timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M')
            else:
                timestamp_str = str(timestamp)[:16] if timestamp != 'N/A' else 'N/A'
            
            message += f"🚨 <b>{tamper_type}</b>\n"
            message += f"Machine: <code>{machine_id}</code>\n"
            message += f"Time: {timestamp_str}\n"
            message += f"Details: {details}\n\n"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search_user command - Search licenses by user info"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "Usage: /search_user <email_or_name>\n"
            "Example: /search_user john@email.com"
        )
        return
    
    search_term = ' '.join(context.args).lower()
    
    try:
        # Get all licenses and search
        all_licenses = firebase.get_all_licenses()
        
        # Filter by creator if assistant
        if role == "assistant":
            assistant = firebase.get_assistant_by_telegram(user_id)
            creator_id = assistant['assistant_id']
            all_licenses = [l for l in all_licenses if l.get('created_by') == creator_id]
        
        # Search in user info
        matches = []
        for lic in all_licenses:
            user_info = lic.get('user_info', {})
            name = user_info.get('name', '').lower()
            email = user_info.get('email', '').lower()
            
            if search_term in name or search_term in email:
                matches.append(lic)
        
        if not matches:
            await update.message.reply_text(f"No licenses found for: {search_term}")
            return
        
        message = f"🔍 <b>SEARCH RESULTS ({len(matches)})</b>\n\n"
        message += f"Search: <i>{search_term}</i>\n\n"
        
        for lic in matches[:10]:  # Show first 10
            key = lic['license_key']
            user_info = lic.get('user_info', {})
            name = user_info.get('name', 'N/A')
            email = user_info.get('email', 'N/A')
            status = lic.get('status', 'unknown')
            
            message += f"<b>{name}</b>\n"
            message += f"Email: {email}\n"
            message += f"License: <code>{key}</code>\n"
            message += f"Status: {status}\n\n"
        
        if len(matches) > 10:
            message += f"... and {len(matches) - 10} more results"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def active_machines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /active_machines command - List all active machines"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    try:
        # Get all licenses
        all_licenses = firebase.get_all_licenses()
        
        # Filter by creator if assistant
        if role == "assistant":
            assistant = firebase.get_assistant_by_telegram(user_id)
            creator_id = assistant['assistant_id']
            all_licenses = [l for l in all_licenses if l.get('created_by') == creator_id]
        
        # Filter active licenses
        active = [l for l in all_licenses if l.get('status') == 'active' and not l.get('is_blocked')]
        
        if not active:
            await update.message.reply_text("No active machines found.")
            return
        
        message = f"✅ <b>ACTIVE MACHINES ({len(active)})</b>\n\n"
        
        for lic in active[:15]:  # Show first 15
            user_info = lic.get('user_info', {})
            name = user_info.get('name', 'N/A')
            machine_id = lic.get('machine_id', 'Not activated')
            last_check = lic.get('last_check_in', 'Never')
            
            # Format last check
            if hasattr(last_check, 'strftime'):
                last_check_str = last_check.strftime('%Y-%m-%d %H:%M')
            else:
                last_check_str = str(last_check)[:16] if last_check != 'Never' else 'Never'
            
            message += f"<b>{name}</b>\n"
            message += f"Machine: <code>{machine_id}</code>\n"
            message += f"Last check: {last_check_str}\n\n"
        
        if len(active) > 15:
            message += f"... and {len(active) - 15} more"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def expired_machines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /expired_machines command - List all expired machines"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    try:
        # Get all licenses
        all_licenses = firebase.get_all_licenses()
        
        # Filter by creator if assistant
        if role == "assistant":
            assistant = firebase.get_assistant_by_telegram(user_id)
            creator_id = assistant['assistant_id']
            all_licenses = [l for l in all_licenses if l.get('created_by') == creator_id]
        
        # Filter expired licenses
        expired = [l for l in all_licenses if l.get('status') == 'expired']
        
        if not expired:
            await update.message.reply_text("No expired machines found.")
            return
        
        message = f"⏰ <b>EXPIRED MACHINES ({len(expired)})</b>\n\n"
        
        for lic in expired[:15]:  # Show first 15
            user_info = lic.get('user_info', {})
            name = user_info.get('name', 'N/A')
            machine_id = lic.get('machine_id', 'Not activated')
            expires_at = lic.get('expires_at', 'N/A')
            
            # Format expiry
            if hasattr(expires_at, 'strftime'):
                expires_str = expires_at.strftime('%Y-%m-%d')
            else:
                expires_str = str(expires_at)[:10] if expires_at != 'N/A' else 'N/A'
            
            message += f"<b>{name}</b>\n"
            message += f"Machine: <code>{machine_id}</code>\n"
            message += f"Expired: {expires_str}\n\n"
        
        if len(expired) > 15:
            message += f"... and {len(expired) - 15} more"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def blocked_machines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /blocked_machines command - List all blocked machines"""
    user_id = update.effective_user.id
    role = get_user_role(user_id)
    
    if role == "none":
        await update.message.reply_text("⚠️ Not authorized.")
        return
    
    try:
        # Get all licenses
        all_licenses = firebase.get_all_licenses()
        
        # Filter by creator if assistant
        if role == "assistant":
            assistant = firebase.get_assistant_by_telegram(user_id)
            creator_id = assistant['assistant_id']
            all_licenses = [l for l in all_licenses if l.get('created_by') == creator_id]
        
        # Filter blocked licenses
        blocked = [l for l in all_licenses if l.get('is_blocked')]
        
        if not blocked:
            await update.message.reply_text("No blocked machines found.")
            return
        
        message = f"🚫 <b>BLOCKED MACHINES ({len(blocked)})</b>\n\n"
        
        for lic in blocked[:15]:  # Show first 15
            user_info = lic.get('user_info', {})
            name = user_info.get('name', 'N/A')
            machine_id = lic.get('machine_id', 'Not activated')
            revoked_at = lic.get('revoked_at', 'N/A')
            
            # Format revoke time
            if hasattr(revoked_at, 'strftime'):
                revoked_str = revoked_at.strftime('%Y-%m-%d %H:%M')
            else:
                revoked_str = str(revoked_at)[:16] if revoked_at != 'N/A' else 'N/A'
            
            message += f"<b>{name}</b>\n"
            message += f"Machine: <code>{machine_id}</code>\n"
            message += f"Blocked: {revoked_str}\n\n"
        
        if len(blocked) > 15:
            message += f"... and {len(blocked) - 15} more"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


# ==================== BULK OPERATIONS ====================

async def bulk_extend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bulk_extend command - Extend all licenses by assistant"""
    user_id = update.effective_user.id
    
    if not is_master_admin(user_id):
        await update.message.reply_text("⚠️ Master admin only.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /bulk_extend <assistant_id> <days>\n"
            "Example: /bulk_extend asst_20251114123456 14"
        )
        return
    
    try:
        assistant_id = context.args[0]
        days = int(context.args[1])
        
        # Verify assistant exists
        assistant = firebase.get_assistant(assistant_id)
        if not assistant:
            await update.message.reply_text(f"❌ Assistant not found: {assistant_id}")
            return
        
        # Get all licenses by this assistant
        licenses = firebase.get_licenses_by_creator(assistant_id)
        
        if not licenses:
            await update.message.reply_text(f"No licenses found for assistant: {assistant_id}")
            return
        
        # Extend each license
        success_count = 0
        for lic in licenses:
            license_key = lic['license_key']
            if firebase.extend_license(license_key, days):
                success_count += 1
        
        message = f"✅ <b>BULK EXTEND COMPLETE</b>\n\n" \
                 f"Assistant: {assistant.get('name')}\n" \
                 f"Extended: {success_count}/{len(licenses)} licenses\n" \
                 f"Days added: {days}"
        
        await update.message.reply_text(message, parse_mode='HTML')
        logger.info(f"Bulk extend: {success_count} licenses by {days} days for {assistant_id}")
        
    except ValueError:
        await update.message.reply_text("❌ Days must be a number")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def bulk_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bulk_revoke command - Revoke all licenses by assistant"""
    user_id = update.effective_user.id
    
    if not is_master_admin(user_id):
        await update.message.reply_text("⚠️ Master admin only.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "Usage: /bulk_revoke <assistant_id> [reason]\n"
            "Example: /bulk_revoke asst_20251114123456 Assistant terminated"
        )
        return
    
    try:
        assistant_id = context.args[0]
        reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "Bulk revocation"
        
        # Verify assistant exists
        assistant = firebase.get_assistant(assistant_id)
        if not assistant:
            await update.message.reply_text(f"❌ Assistant not found: {assistant_id}")
            return
        
        # Get all licenses by this assistant
        licenses = firebase.get_licenses_by_creator(assistant_id)
        
        if not licenses:
            await update.message.reply_text(f"No licenses found for assistant: {assistant_id}")
            return
        
        # Ask for confirmation
        message = f"⚠️ <b>CONFIRMATION REQUIRED</b>\n\n" \
                 f"This will revoke ALL {len(licenses)} licenses created by:\n" \
                 f"<b>{assistant.get('name')}</b> ({assistant_id})\n\n" \
                 f"Reason: {reason}\n\n" \
                 f"To confirm, send: /bulk_revoke_confirm {assistant_id}"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def bulk_revoke_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bulk_revoke_confirm command - Confirm bulk revocation"""
    user_id = update.effective_user.id
    
    if not is_master_admin(user_id):
        await update.message.reply_text("⚠️ Master admin only.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /bulk_revoke_confirm <assistant_id>")
        return
    
    try:
        assistant_id = context.args[0]
        
        # Get all licenses by this assistant
        licenses = firebase.get_licenses_by_creator(assistant_id)
        
        if not licenses:
            await update.message.reply_text(f"No licenses found for assistant: {assistant_id}")
            return
        
        # Revoke each license
        success_count = 0
        for lic in licenses:
            license_key = lic['license_key']
            if firebase.revoke_license(license_key, "Bulk revocation"):
                success_count += 1
        
        message = f"🚫 <b>BULK REVOKE COMPLETE</b>\n\n" \
                 f"Revoked: {success_count}/{len(licenses)} licenses\n" \
                 f"Assistant: {assistant_id}"
        
        await update.message.reply_text(message, parse_mode='HTML')
        logger.info(f"Bulk revoke: {success_count} licenses for {assistant_id}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /export_data command - Export assistant's data as JSON"""
    user_id = update.effective_user.id
    
    if not is_master_admin(user_id):
        await update.message.reply_text("⚠️ Master admin only.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "Usage: /export_data <assistant_id>\n"
            "Example: /export_data asst_20251114123456"
        )
        return
    
    try:
        assistant_id = context.args[0]
        
        # Get assistant data
        assistant = firebase.get_assistant(assistant_id)
        if not assistant:
            await update.message.reply_text(f"❌ Assistant not found: {assistant_id}")
            return
        
        # Get all licenses by this assistant
        licenses = firebase.get_licenses_by_creator(assistant_id)
        
        # Prepare export data
        export = {
            'assistant': {
                'id': assistant_id,
                'name': assistant.get('name'),
                'email': assistant.get('email'),
                'telegram_id': assistant.get('telegram_id'),
                'created_at': str(assistant.get('created_at')),
                'is_active': assistant.get('is_active')
            },
            'licenses': [],
            'statistics': {
                'total': len(licenses),
                'active': sum(1 for l in licenses if l.get('status') == 'active'),
                'pending': sum(1 for l in licenses if l.get('status') == 'pending'),
                'expired': sum(1 for l in licenses if l.get('status') == 'expired'),
                'revoked': sum(1 for l in licenses if l.get('is_blocked'))
            }
        }
        
        # Add license details
        for lic in licenses:
            license_info = {
                'license_key': lic['license_key'],
                'user': lic.get('user_info', {}),
                'status': lic.get('status'),
                'is_blocked': lic.get('is_blocked', False),
                'machine_id': lic.get('machine_id'),
                'created_at': str(lic.get('created_at')),
                'expires_at': str(lic.get('expires_at')),
                'trial_days': lic.get('trial_days')
            }
            export['licenses'].append(license_info)
        
        # Convert to JSON
        import json
        json_data = json.dumps(export, indent=2)
        
        # Send as file
        from io import BytesIO
        file_buffer = BytesIO(json_data.encode('utf-8'))
        file_buffer.name = f"export_{assistant_id}.json"
        
        await update.message.reply_document(
            document=file_buffer,
            filename=f"export_{assistant_id}.json",
            caption=f"📦 Export for {assistant.get('name')}\n"
                   f"Total licenses: {len(licenses)}"
        )
        
        logger.info(f"Data exported for {assistant_id}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


def main():
    """Start the bot"""
    # Initialize Firebase
    init_firebase()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # License management
    application.add_handler(CommandHandler("create_license", create_license))
    application.add_handler(CommandHandler("list_licenses", list_licenses))
    application.add_handler(CommandHandler("my_licenses", my_licenses))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("revoke", revoke))
    application.add_handler(CommandHandler("unrevoke", unrevoke))
    application.add_handler(CommandHandler("extend", extend))
    application.add_handler(CommandHandler("set_expiry", set_expiry))
    
    # Assistant management (Master only)
    application.add_handler(CommandHandler("add_assistant", add_assistant))
    application.add_handler(CommandHandler("list_assistants", list_assistants))
    application.add_handler(CommandHandler("remove_assistant", remove_assistant))
    application.add_handler(CommandHandler("toggle_assistant", toggle_assistant))
    
    # Statistics
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("my_stats", my_stats))
    
    # Monitoring commands
    application.add_handler(CommandHandler("logs", logs))
    application.add_handler(CommandHandler("tamper_logs", tamper_logs))
    application.add_handler(CommandHandler("search_user", search_user))
    application.add_handler(CommandHandler("active_machines", active_machines))
    application.add_handler(CommandHandler("expired_machines", expired_machines))
    application.add_handler(CommandHandler("blocked_machines", blocked_machines))
    
    # Bulk operations (Master only)
    application.add_handler(CommandHandler("bulk_extend", bulk_extend))
    application.add_handler(CommandHandler("bulk_revoke", bulk_revoke))
    application.add_handler(CommandHandler("bulk_revoke_confirm", bulk_revoke_confirm))
    application.add_handler(CommandHandler("export_data", export_data))
    
    # Start the bot
    logger.info("✅ Bot started successfully!")
    logger.info("📱 Send /start to your bot to begin...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
