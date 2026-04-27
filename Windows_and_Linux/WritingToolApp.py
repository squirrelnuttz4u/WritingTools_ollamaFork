import gettext
import json
import logging
import os
import signal
import sys
import threading
import time

import darkdetect
import pyperclip
import ui.AboutWindow
import ui.CustomPopupWindow
import ui.OnboardingWindow
import ui.ResponseWindow
import ui.SettingsWindow
from aiprovider import OllamaProvider
from pynput import keyboard as pykeyboard
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QLocale, Signal, Slot
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox
from update_checker import UpdateChecker

from ui.UIUtils import app_dir

_ = gettext.gettext


# Baked-in default action buttons. Used as a fallback when options.json is
# missing next to the exe (first-run, fresh install without the file, etc.).
# Kept in sync with Windows_and_Linux/options.json - the CI workflow ships
# that file in the release zip as the editable source of truth. Users change
# buttons via the UI, which writes back to options.json; this dict is never
# consulted again once the file exists on disk.
DEFAULT_OPTIONS = {
    "Proofread": {
        "prefix": "Proofread this:\n\n",
        "instruction": "You are a grammar proofreading assistant.\nOutput ONLY the corrected text without any additional comments.\nMaintain the original text structure and writing style.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.\nIf the text is absolutely incompatible with this (e.g., totally random gibberish), output \"ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST\".",
        "icon": "icons/magnifying-glass",
        "open_in_window": False,
    },
    "Rewrite": {
        "prefix": "Rewrite this:\n\n",
        "instruction": "You are a writing assistant.\nRewrite the text provided by the user to improve phrasing.\nOutput ONLY the rewritten text without additional comments.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.\nIf the text is absolutely incompatible with proofreading (e.g., totally random gibberish), output \"ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST\".",
        "icon": "icons/rewrite",
        "open_in_window": False,
    },
    "Professional": {
        "prefix": "Make this more professional:\n\n",
        "instruction": "You are a writing assistant.\nRewrite the text provided by the user to be more professional. Output ONLY the professional text without additional comments.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.\nIf the text is absolutely incompatible with rewriting (e.g., totally random gibberish), output \"ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST\".",
        "icon": "icons/briefcase",
        "open_in_window": False,
    },
    "Concise": {
        "prefix": "Make this more concise:\n\n",
        "instruction": "You are a writing assistant.\nRewrite the text provided by the user to be more concise.\nOutput ONLY the concise text without additional comments.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.\nIf the text is absolutely incompatible with rewriting (e.g., totally random gibberish), output \"ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST\".",
        "icon": "icons/concise",
        "open_in_window": False,
    },
    "Friendly": {
        "prefix": "Make this more friendly:\n\n",
        "instruction": "You are a writing assistant.\nRewrite the text provided by the user to be more friendly while remaining professional.\nOutput ONLY the friendly text without additional comments.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.\nIf the text is absolutely incompatible with rewriting (e.g., totally random gibberish), output \"ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST\".",
        "icon": "icons/smiley-face",
        "open_in_window": False,
    },
    "Email Reply": {
        "prefix": "Draft a reply to this email:\n\n",
        "instruction": "You are an assistant that drafts email replies for an ACNR employee.\nThe user will paste an email they received. Draft a concise, professional, courteous reply in the first person, matching the voice of a business professional at American Consolidated Natural Resources, Inc.\nAcknowledge the sender's points briefly, answer any questions, and propose clear next steps if warranted. Do not invent commitments, dates, people, or attachments that are not supported by the input.\nOutput ONLY the reply body (no 'Subject:' line, no 'From:'/'To:' headers). Include a greeting and a short sign-off only when appropriate.\nRespond in the same language as the email.\nIf the input is not an email, output \"ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST\".",
        "icon": "icons/send",
        "open_in_window": True,
    },
    "Summary": {
        "prefix": "Summarize this:\n\n",
        "instruction": "You are a summarization assistant.\nProvide a succinct summary of the text provided by the user.\nThe summary should be succinct yet encompass all the key insightful points.\n\nTo make it quite legible and readable, you should use Markdown formatting (bold, italics, codeblocks...) as appropriate.\nYou should also add a little line spacing between your paragraphs as appropriate.\nAnd only if appropriate, you could also use headings (only the very small ones), lists, tables, etc.\n\nDon't be repetitive or too verbose.\nOutput ONLY the summary without additional comments.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.\nIf the text is absolutely incompatible with summarisation (e.g., totally random gibberish), output \"ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST\".",
        "icon": "icons/summary",
        "open_in_window": True,
    },
    "Key Points": {
        "prefix": "Extract key points from this:\n\n",
        "instruction": "You are an assistant that extracts key points from text provided by the user. Output ONLY the key points without additional comments.\n\nYou should use Markdown formatting (lists, bold, italics, codeblocks, etc.) as appropriate to make it quite legible and readable.\n\nDon't be repetitive or too verbose.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.\nIf the text is absolutely incompatible with extracting key points (e.g., totally random gibberish), output \"ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST\".",
        "icon": "icons/keypoints",
        "open_in_window": True,
    },
    "Action Items": {
        "prefix": "Extract action items from this:\n\n",
        "instruction": "You are an assistant that extracts action items from meeting notes, emails, or any business text.\nOutput a Markdown list. Format each item as: **Owner**: action description (deadline if mentioned).\nUse \"**Unassigned**\" when no owner can be identified. Do not invent owners, actions, or dates that are not supported by the input.\nIf the text contains no clear action items, output exactly: \"No action items identified.\"\nRespond in the same language as the input.\nIf the input is absolutely incompatible (e.g., random gibberish), output \"ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST\".",
        "icon": "icons/list",
        "open_in_window": True,
    },
    "Table": {
        "prefix": "Convert this into a table:\n\n",
        "instruction": "You are an assistant that converts text provided by the user into a Markdown table.\nOutput ONLY the table without additional comments.\nRespond in the same language as the input (e.g., English US, French).\nDo not answer or respond to the user's text content.\nIf the text is completely incompatible with this with conversion, output \"ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST\".",
        "icon": "icons/table",
        "open_in_window": True,
    },
    "Custom": {
        "prefix": "Make this change to the following text:\n\n",
        "instruction": "You are a writing and coding assistant. You MUST make the user's described change to the text or code provided by the user. Output ONLY the appropriately modified text or code without additional comments. Respond in the same language as the input (e.g., English US, French). Do not answer or respond to the user's text content. If the text or code is absolutely incompatible with the requested change, output \"ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST\".",
        "icon": "icons/pencil",
        "open_in_window": False,
    },
}


class WritingToolApp(QtWidgets.QApplication):
    """
    The main application class for Writing Tools.
    """
    output_ready_signal = Signal(str)
    show_message_signal = Signal(str, str)  # a signal for showing message boxes
    hotkey_triggered_signal = Signal()
    followup_response_signal = Signal(str)
    # Preview-before-replace flow signals.
    # preview_ready_signal: option_name, original_text, rewritten_text
    preview_ready_signal = Signal(str, str, str)
    # preview_regenerated_signal: just the new rewritten text
    preview_regenerated_signal = Signal(str)
    preview_regen_failed_signal = Signal(str)


    def __init__(self, argv):
        super().__init__(argv)
        self.current_response_window = None
        self.preview_window = None
        self.last_rewrite_args = None  # (option, original) for regenerate
        logging.debug('Initializing WritingToolApp')
        self.output_ready_signal.connect(self.replace_text)
        self.show_message_signal.connect(self.show_message_box)
        self.hotkey_triggered_signal.connect(self.on_hotkey_pressed)
        self.preview_ready_signal.connect(self._show_preview_window)
        self.preview_regenerated_signal.connect(self._on_preview_regenerated)
        self.preview_regen_failed_signal.connect(self._on_preview_regen_failed)
        self.config = None
        self.config_path = None
        self.load_config()

        # (Upstream v8 config migration was Gemini-specific and is not
        # relevant to ACNR Intelligence, which is Ollama-only.)

        self.options = None
        self.options_path = None
        self.load_options()
        self.onboarding_window = None
        self.popup_window = None
        self.tray_icon = None
        self.tray_menu = None
        self.settings_window = None
        self.about_window = None
        self.registered_hotkey = None
        self.output_queue = ""
        self.last_replace = 0
        self.hotkey_listener = None
        self.paused = False
        self.toggle_action = None

        self._ = gettext.gettext

        # Initialize the ctrl+c hotkey listener
        self.ctrl_c_timer = None
        self.setup_ctrl_c_listener()

        # Setup available AI providers
        self.providers = [OllamaProvider(self)]

        if not self.config:
            logging.debug('No config found, showing onboarding')
            self.show_onboarding()
        else:
            logging.debug('Config found, setting up hotkey and tray icon')

            # Initialize the current provider (ACNR Intelligence is Ollama-only)
            provider_name = self.config.get('provider', 'Ollama (For Experts)')

            self.current_provider = next((provider for provider in self.providers if provider.provider_name == provider_name), None)
            if not self.current_provider:
                logging.warning(f'Provider {provider_name} not found. Using default provider.')
                self.current_provider = self.providers[0]

            self.current_provider.load_config(self.config.get("providers", {}).get(provider_name, {}))

            self.create_tray_icon()
            self.register_hotkey()

            try:
                lang = self.config['locale']
            except KeyError:
                lang = None
            self.change_language(lang)

            # Initialize update checker
            self.update_checker = UpdateChecker(self)
            self.update_checker.check_updates_async()

        self.recent_triggers = []  # Track recent hotkey triggers
        self.TRIGGER_WINDOW = 1.5  # Time window in seconds
        self.MAX_TRIGGERS = 3  # Max allowed triggers in window

    def setup_translations(self, lang=None):
        if not lang:
            lang = QLocale.system().name().split('_')[0]

        try:
            translation = gettext.translation(
                'messages',
                localedir=os.path.join(os.path.dirname(__file__), 'locales'),
                languages=[lang]
            )
        except FileNotFoundError:
            translation = gettext.NullTranslations()

        translation.install()
        # Update the translation function for all UI components.
        self._ = translation.gettext
        ui.AboutWindow._ = self._
        ui.SettingsWindow._ = self._
        ui.ResponseWindow._ = self._
        ui.OnboardingWindow._ = self._
        ui.CustomPopupWindow._ = self._

    def retranslate_ui(self):
        self.update_tray_menu()

    def change_language(self, lang):
        self.setup_translations(lang)
        self.retranslate_ui()

        # Update all other windows
        for widget in QApplication.topLevelWidgets():
            if widget != self and hasattr(widget, 'retranslate_ui'):
                widget.retranslate_ui()

    def check_trigger_spam(self):
        """
        Check if hotkey is being triggered too frequently (3+ times in 1.5 seconds).
        Returns True if spam is detected.
        """
        current_time = time.time()
        
        # Add current trigger
        self.recent_triggers.append(current_time)
        
        # Remove old triggers outside the window
        self.recent_triggers = [t for t in self.recent_triggers 
                            if current_time - t <= self.TRIGGER_WINDOW]
        
        # Check if we have too many triggers in the window
        return len(self.recent_triggers) >= self.MAX_TRIGGERS

    def load_config(self):
        """
        Load the configuration file.
        """
        self.config_path = os.path.join(app_dir(), 'config.json')
        logging.debug(f'Loading config from {self.config_path}')
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
                logging.debug('Config loaded successfully')
        else:
            logging.debug('Config file not found')
            self.config = None

    def load_options(self):
        """
        Load the action-button options from options.json next to the exe.
        If the file is missing (e.g. it wasn't shipped alongside the binary,
        or a user deleted it) we self-heal from the baked-in defaults so the
        app never launches with an empty action menu. Users can still edit
        buttons normally; the UI writes back to the same options.json.
        """
        self.options_path = os.path.join(app_dir(), 'options.json')
        logging.debug(f'Loading options from {self.options_path}')
        if os.path.exists(self.options_path):
            with open(self.options_path, 'r', encoding='utf-8') as f:
                self.options = json.load(f)
                logging.debug('Options loaded successfully')
            return

        logging.info('options.json missing; writing baked-in ACNR defaults.')
        self.options = dict(DEFAULT_OPTIONS)
        try:
            with open(self.options_path, 'w', encoding='utf-8') as f:
                json.dump(self.options, f, indent=2, ensure_ascii=False)
        except OSError as e:
            # Read-only install dir (or sandbox); keep the in-memory copy.
            logging.warning(f'Could not write default options.json: {e}')

    def save_config(self, config):
        """
        Save the configuration file.
        """
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=4)
            logging.debug('Config saved successfully')
        self.config = config

    def show_onboarding(self):
        """
        Show the onboarding window for first-time users.
        """
        logging.debug('Showing onboarding window')
        self.onboarding_window = ui.OnboardingWindow.OnboardingWindow(self)
        self.onboarding_window.close_signal.connect(self.exit_app)
        self.onboarding_window.show()

    def start_hotkey_listener(self):
        """
        Create listener for hotkeys on Linux/Mac.
        """
        orig_shortcut = self.config.get('shortcut', 'ctrl+space')
        # Parse the shortcut string, for example ctrl+alt+h -> <ctrl>+<alt>+h
        shortcut = '+'.join([f'{t}' if len(t) <= 1 else f'<{t}>' for t in orig_shortcut.split('+')])
        logging.debug(f'Registering global hotkey for shortcut: {shortcut}')
        try:
            if self.hotkey_listener is not None:
                self.hotkey_listener.stop()

            def on_activate():
                if self.paused:
                    return
                logging.debug('triggered hotkey')
                self.hotkey_triggered_signal.emit()  # Emit the signal when hotkey is pressed

            # Define the hotkey combination
            hotkey = pykeyboard.HotKey(
                pykeyboard.HotKey.parse(shortcut),
                on_activate
            )
            self.registered_hotkey = orig_shortcut

            # Helper function to standardize key event
            def for_canonical(f):
                return lambda k: f(self.hotkey_listener.canonical(k))

            # Create a listener and store it as an attribute to stop it later
            self.hotkey_listener = pykeyboard.Listener(
                on_press=for_canonical(hotkey.press),
                on_release=for_canonical(hotkey.release)
            )

            # Start the listener
            self.hotkey_listener.start()
        except Exception as e:
            logging.error(f'Failed to register hotkey: {e}')

    def register_hotkey(self):
        """
        Register the global hotkey for activating Writing Tools.
        """
        logging.debug('Registering hotkey')
        self.start_hotkey_listener()
        logging.debug('Hotkey registered')

    def on_hotkey_pressed(self):
        """
        Handle the hotkey press event.
        """
        logging.debug('Hotkey pressed')
        
        # Check for spam triggers
        if self.check_trigger_spam():
            logging.warning('Hotkey spam detected - quitting application')
            self.exit_app()
            return
            
        # Original hotkey handling continues...
        if self.current_provider:
            logging.debug("Cancelling current provider's request")
            self.current_provider.cancel()
            self.output_queue = ""

        # noinspection PyTypeChecker
        QtCore.QMetaObject.invokeMethod(self, "_show_popup", QtCore.Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _show_popup(self):
        """
        Show the popup window when the hotkey is pressed.
        """
        logging.debug('Showing popup window')
        # First attempt with default sleep
        selected_text = self.get_selected_text()

        # Retry with longer sleep if no text captured
        if not selected_text:
            logging.debug('No text captured, retrying with longer sleep')
            selected_text = self.get_selected_text(sleep_duration=0.5)

        logging.debug(f'Selected text: "{selected_text}"')
        try:
            if self.popup_window is not None:
                logging.debug('Existing popup window found')
                if self.popup_window.isVisible():
                    logging.debug('Closing existing visible popup window')
                    self.popup_window.close()
                self.popup_window = None
            logging.debug('Creating new popup window')
            self.popup_window = ui.CustomPopupWindow.CustomPopupWindow(self, selected_text)

            # Set the window icon
            icon_path = os.path.join(app_dir(), 'icons', 'app_icon.png')
            if os.path.exists(icon_path): self.setWindowIcon(QtGui.QIcon(icon_path))
            # Get the screen containing the cursor
            cursor_pos = QCursor.pos()
            screen = QGuiApplication.screenAt(cursor_pos)
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            screen_geometry = screen.geometry()
            logging.debug(f'Cursor is on screen: {screen.name()}')
            logging.debug(f'Screen geometry: {screen_geometry}')
            # Show the popup to get its size
            self.popup_window.show()
            self.popup_window.adjustSize()
            # Ensure the popup it's focused, even on lower-end machines
            self.popup_window.activateWindow()
            QtCore.QTimer.singleShot(100, self.popup_window.custom_input.setFocus)

            popup_width = self.popup_window.width()
            popup_height = self.popup_window.height()
            # Calculate position
            x = cursor_pos.x()
            y = cursor_pos.y() + 20  # 20 pixels below cursor
            # Adjust if the popup would go off the right edge of the screen
            if x + popup_width > screen_geometry.right():
                x = screen_geometry.right() - popup_width
            # Adjust if the popup would go off the bottom edge of the screen
            if y + popup_height > screen_geometry.bottom():
                y = cursor_pos.y() - popup_height - 10  # 10 pixels above cursor
            self.popup_window.move(x, y)
            logging.debug(f'Popup window moved to position: ({x}, {y})')
        except Exception as e:
            logging.error(f'Error showing popup window: {e}', exc_info=True)

    def get_selected_text(self, sleep_duration=0.2):
        """
        Get the currently selected text from any application.
        Args:
            sleep_duration (float): Time to wait for clipboard update
        """
        # Backup the clipboard
        clipboard_backup = pyperclip.paste()
        logging.debug(f'Clipboard backup: "{clipboard_backup}" (sleep: {sleep_duration}s)')

        # Clear the clipboard
        self.clear_clipboard()

        # Simulate Ctrl+C
        logging.debug('Simulating Ctrl+C')
        kbrd = pykeyboard.Controller()

        def press_ctrl_c():
            kbrd.press(pykeyboard.Key.ctrl.value)
            kbrd.press('c')
            kbrd.release('c')
            kbrd.release(pykeyboard.Key.ctrl.value)

        press_ctrl_c()

        # Wait for the clipboard to update
        time.sleep(sleep_duration)
        logging.debug(f'Waited {sleep_duration}s for clipboard')

        # Get the selected text
        selected_text = pyperclip.paste()

        # Restore the clipboard
        pyperclip.copy(clipboard_backup)

        return selected_text

    @staticmethod
    def clear_clipboard():
        """
        Clear the system clipboard.
        """
        try:
            pyperclip.copy('')
        except Exception as e:
            logging.error(f'Error clearing clipboard: {e}')

    def process_option(self, option, selected_text, custom_change=None):
        """
        Process the selected writing option in a separate thread.
        """
        logging.debug(f'Processing option: {option}')

        # For Summary, Key Points, Table, and empty text custom prompts, create response window
        if (option == 'Custom' and not selected_text.strip()) or self.options[option]['open_in_window']:
            window_title = "Chat" if (option == 'Custom' and not selected_text.strip()) else option
            self.current_response_window = self.show_response_window(window_title, selected_text)
            
            # Initialize chat history with text/prompt
            if option == 'Custom' and not selected_text.strip():
                # For direct AI queries, don't include empty text
                self.current_response_window.chat_history = []
            else:
                # For other options, include the original text
                self.current_response_window.chat_history = [
                    {
                        "role": "user",
                        "content": f"Original text to {option.lower()}:\n\n{selected_text}"
                    }
                ]
        else:
            # Clear any existing response window reference for non-window options
            if hasattr(self, 'current_response_window'):
                delattr(self, 'current_response_window')
                
        threading.Thread(target=self.process_option_thread, args=(option, selected_text, custom_change), daemon=True).start()

    def process_option_thread(self, option, selected_text, custom_change=None):
            """
            Thread function to process the selected writing option using the AI model.
            """
            logging.debug(f'Starting processing thread for option: {option}')
            try:
                if selected_text.strip() == '':
                    # No selected text
                    if option == 'Custom':
                        prompt = custom_change
                        system_instruction = "You are a friendly, helpful, compassionate, and endearing AI conversational assistant. Avoid making assumptions or generating harmful, biased, or inappropriate content. When in doubt, do not make up information. Ask the user for clarification if needed. Try not be unnecessarily repetitive in your response. You can, and should as appropriate, use Markdown formatting to make your response nicely readable."
                    else:
                        self.show_message_signal.emit('Error', 'Please select text to use this option.')
                        return
                else:
                    selected_prompt = self.options.get(option, ('', ''))
                    prompt_prefix = selected_prompt['prefix']
                    system_instruction = selected_prompt['instruction']
                    if option == 'Custom':
                        prompt = f"{prompt_prefix}Described change: {custom_change}\n\nText: {selected_text}"
                    else:
                        prompt = f"{prompt_prefix}{selected_text}"

                self.output_queue = ""

                logging.debug(f'Getting response from provider for option: {option}')

                if (option == 'Custom' and not selected_text.strip()) or self.options[option]['open_in_window']:
                    logging.debug('Getting response for window display')
                    response = self.current_provider.get_response(system_instruction, prompt, return_response=True)
                    logging.debug(f'Got response of length: {len(response) if response else 0}')
                    
                    # For custom prompts with no text, add question to chat history
                    if option == 'Custom' and not selected_text.strip():
                        self.current_response_window.chat_history.append({
                            "role": "user",
                            "content": custom_change
                        })
                    
                    # Set initial response using QMetaObject.invokeMethod to ensure thread safety
                    if hasattr(self, 'current_response_window'):
                        # noinspection PyTypeChecker
                        QtCore.QMetaObject.invokeMethod(
                            self.current_response_window,
                            'set_text',
                            QtCore.Qt.ConnectionType.QueuedConnection,
                            QtCore.Q_ARG(str, response)
                        )
                        logging.debug('Invoked set_text on response window')
                else:
                    logging.debug('Getting response for preview-and-confirm')
                    response = self.current_provider.get_response(
                        system_instruction, prompt, return_response=True
                    )
                    if not response:
                        return
                    text = response.strip()
                    error_message = 'ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST'
                    if text == error_message:
                        self.show_message_signal.emit(
                            'Error',
                            'The text is incompatible with the requested change.'
                        )
                        return
                    self.last_rewrite_args = (option, selected_text)
                    self.preview_ready_signal.emit(option, selected_text, text)
                    logging.debug('Preview ready')

            except Exception as e:
                logging.error(f'An error occurred: {e}', exc_info=True)

                self.show_message_signal.emit('Error', f'An error occurred: {e}')

    @Slot(str, str)
    def show_message_box(self, title, message):
        """
        Show a message box with the given title and message.
        """
        QMessageBox.warning(None, title, message)

    def show_response_window(self, option, text):
        """
        Show the response in a new window instead of pasting it.
        """
        response_window = ui.ResponseWindow.ResponseWindow(self, f"{option} Result")
        response_window.selected_text = text  # Store the text for regeneration
        response_window.show()
        return response_window

    def replace_text(self, new_text):
        """
        Replaces the text by pasting in the LLM generated text. With "Key Points" and "Summary", invokes a window with the output instead.
        """
        error_message = 'ERROR_TEXT_INCOMPATIBLE_WITH_REQUEST'

        # Confirm new_text exists and is a string
        if new_text and isinstance(new_text, str):
            self.output_queue += new_text
            current_output = self.output_queue.strip()  # Strip whitespace for comparison

            # If the new text is the error message, show a message box
            if current_output == error_message:
                self.show_message_signal.emit('Error', 'The text is incompatible with the requested change.')
                return

            # Check if we're building up to the error message (to prevent partial pasting)
            if len(current_output) <= len(error_message):
                clean_current = ''.join(current_output.split())
                clean_error = ''.join(error_message.split())
                if clean_current == clean_error[:len(clean_current)]:
                    return

            logging.debug('Processing output text')
            try:
                # For Summary and Key Points, show in response window
                if hasattr(self, 'current_response_window'):
                    self.current_response_window.append_text(new_text)
                    
                    # If this is the initial response, add it to chat history
                    if len(self.current_response_window.chat_history) == 1:  # Only original text exists
                        self.current_response_window.chat_history.append({
                            "role": "assistant",
                            "content": self.output_queue.rstrip('\n')
                        })
                else:
                    # For other options, use the original clipboard-based replacement
                    clipboard_backup = pyperclip.paste()
                    cleaned_text = self.output_queue.rstrip('\n')
                    pyperclip.copy(cleaned_text)
                    
                    kbrd = pykeyboard.Controller()
                    def press_ctrl_v():
                        kbrd.press(pykeyboard.Key.ctrl.value)
                        kbrd.press('v')
                        kbrd.release('v')
                        kbrd.release(pykeyboard.Key.ctrl.value)

                    press_ctrl_v()
                    time.sleep(0.2)
                    pyperclip.copy(clipboard_backup)

                if not hasattr(self, 'current_response_window'):
                    self.output_queue = ""

            except Exception as e:
                logging.error(f'Error processing output: {e}')
        else:
            logging.debug('No new text to process')

    # ------------------------------------------------------------------
    # Preview-before-replace flow
    # ------------------------------------------------------------------
    @Slot(str, str, str)
    def _show_preview_window(self, option, original, rewrite):
        """Open a confirmation window before pasting the rewrite."""
        from ui.PreviewWindow import PreviewWindow
        if self.preview_window is not None:
            self.preview_window.close()
        self.preview_window = PreviewWindow(option, original, rewrite)
        self.preview_window.accepted.connect(self._apply_rewrite)
        self.preview_window.regenerate.connect(self._on_preview_regenerate)
        self.preview_window.destroyed.connect(self._on_preview_closed)

        # Center near the screen the cursor is on, like the popup does.
        screen = self.primaryScreen().geometry()
        w, h = self.preview_window.width(), self.preview_window.height()
        self.preview_window.move(
            screen.x() + (screen.width() - w) // 2,
            screen.y() + (screen.height() - h) // 2,
        )

        self.preview_window.show()
        self.preview_window.raise_()
        self.preview_window.activateWindow()

    @Slot(str)
    def _apply_rewrite(self, text):
        """User clicked Accept: paste the rewrite into the source app."""
        # Hide the preview first so focus returns to whatever was active
        # when the popup originally opened (Outlook / Word / browser / etc.).
        if self.preview_window is not None:
            self.preview_window.hide()
        QtCore.QTimer.singleShot(150, lambda: self._do_paste(text))

    def _do_paste(self, text):
        """Clipboard + simulated Ctrl+V, restoring the user's prior clipboard."""
        try:
            clipboard_backup = pyperclip.paste()
        except Exception:
            clipboard_backup = ''
        try:
            pyperclip.copy(text)
            kbrd = pykeyboard.Controller()
            kbrd.press(pykeyboard.Key.ctrl.value)
            kbrd.press('v')
            kbrd.release('v')
            kbrd.release(pykeyboard.Key.ctrl.value)
            time.sleep(0.2)
        finally:
            try:
                pyperclip.copy(clipboard_backup)
            except Exception:
                pass

    def _on_preview_regenerate(self):
        """User clicked Regenerate: re-run the same option on the same input."""
        if not self.last_rewrite_args:
            return
        option, original = self.last_rewrite_args
        threading.Thread(
            target=self._regenerate_thread,
            args=(option, original),
            daemon=True,
        ).start()

    def _regenerate_thread(self, option, original):
        try:
            selected_prompt = self.options.get(option, {})
            prefix = selected_prompt.get('prefix', '')
            system_instruction = selected_prompt.get('instruction', '')
            prompt = f"{prefix}{original}"
            response = self.current_provider.get_response(
                system_instruction, prompt, return_response=True
            )
            if response:
                self.preview_regenerated_signal.emit(response.strip())
            else:
                self.preview_regen_failed_signal.emit(
                    "Empty response from the model. Try again or discard."
                )
        except Exception as e:
            logging.exception('Regenerate failed')
            self.preview_regen_failed_signal.emit(f"Regenerate failed: {e}")

    @Slot(str)
    def _on_preview_regenerated(self, text):
        if self.preview_window is not None:
            self.preview_window.update_rewrite(text)

    @Slot(str)
    def _on_preview_regen_failed(self, message):
        if self.preview_window is not None:
            self.preview_window.show_error(message)

    def _on_preview_closed(self):
        self.preview_window = None
        self.last_rewrite_args = None

    def create_tray_icon(self):
        """
        Create the system tray icon for the application.

        Failure modes seen on Windows in production:
          - QSystemTrayIcon constructed without a valid icon doesn't render
            at all (the tray slot is silently dropped). Always provide one.
          - Some locked-down corporate Windows builds report
            isSystemTrayAvailable()==False; nothing we can do but log so
            users know to look elsewhere.
        """
        if self.tray_icon:
            logging.debug('Tray icon already exists')
            return

        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            logging.error(
                'System tray is not available on this system. The app will '
                'still respond to the global hotkey, but Settings/About/Quit '
                'will not be reachable. Use the in-popup gear/menu instead.'
            )
            return

        # Try several known locations for the tray icon. app_dir()/icons is the
        # canonical install layout; we also accept a flat next-to-exe layout
        # because that's what an absolute-minimum debug install looks like.
        candidates = [
            os.path.join(app_dir(), 'icons', 'app_icon.png'),
            os.path.join(app_dir(), 'icons', 'app_icon.ico'),
            os.path.join(app_dir(), 'app_icon.png'),
            os.path.join(app_dir(), 'app_icon.ico'),
        ]
        icon_path = next((p for p in candidates if os.path.exists(p)), None)

        if icon_path:
            logging.info(f'Creating tray icon from {icon_path}')
            self.tray_icon = QtWidgets.QSystemTrayIcon(QtGui.QIcon(icon_path), self)
        else:
            logging.error(
                'Tray icon image not found. Looked in: %s. Falling back to '
                'the application style icon so the tray slot is still '
                'visible (Windows hides icon-less tray entries).',
                ', '.join(candidates),
            )
            fallback = self.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon
            )
            self.tray_icon = QtWidgets.QSystemTrayIcon(fallback, self)

        self.tray_icon.setToolTip("ACNR Intelligence")
        self.tray_menu = QtWidgets.QMenu()
        self.tray_icon.setContextMenu(self.tray_menu)

        # Single-click to open settings is a common Windows expectation.
        # The right-click context menu (Settings/Pause/About/Exit) still works.
        self.tray_icon.activated.connect(self._on_tray_activated)

        self.update_tray_menu()
        self.tray_icon.show()
        if self.tray_icon.isVisible():
            logging.info('Tray icon displayed.')
        else:
            logging.error(
                'Tray icon was created but isVisible()==False. Windows may '
                'have hidden it under the chevron - click the upward arrow '
                'in the system tray to find it, then drag it onto the bar.'
            )

    def _on_tray_activated(self, reason):
        """Open Settings on left-click; right-click already shows the menu."""
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            self.show_settings()

    def update_tray_menu(self):
        """
        Update the tray menu with all menu items, including pause functionality
        and proper translations.
        """
        self.tray_menu.clear()

        # Apply dark mode styles using darkdetect
        self.apply_dark_mode_styles(self.tray_menu)

        # Settings menu item
        settings_action = self.tray_menu.addAction(self._('Settings'))
        settings_action.triggered.connect(self.show_settings)

        # Pause/Resume toggle action 
        self.toggle_action = self.tray_menu.addAction(self._('Resume') if self.paused else self._('Pause'))
        self.toggle_action.triggered.connect(self.toggle_paused)

        # About menu item
        about_action = self.tray_menu.addAction(self._('About'))
        about_action.triggered.connect(self.show_about)

        # Exit menu item
        exit_action = self.tray_menu.addAction(self._('Exit'))
        exit_action.triggered.connect(self.exit_app)
        
    def toggle_paused(self):
        """Toggle the paused state of the application."""
        logging.debug('Toggle paused state')
        self.paused = not self.paused
        self.toggle_action.setText(self._('Resume') if self.paused else self._('Pause'))
        logging.debug('App is paused' if self.paused else 'App is resumed')

    @staticmethod
    def apply_dark_mode_styles(menu):
        """
        Apply styles to the tray menu based on system theme using darkdetect.
        """
        is_dark_mode = darkdetect.isDark()
        palette = menu.palette()

        if is_dark_mode:
            logging.debug('Tray icon dark')
            # Dark mode colors
            palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#2d2d2d"))  # Dark background
            palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#ffffff"))  # White text
        else:
            logging.debug('Tray icon light')
            # Light mode colors
            palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#ffffff"))  # Light background
            palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#000000"))  # Black text

        menu.setPalette(palette)


    """
    The function below (process_followup_question) processes follow-up questions in the chat interface for Summary, Key Points, and Table operations.

    This method handles the complex interaction between the UI, chat history, and AI providers:

    1. Chat History Management:
    - Maintains a list of all messages (original text, summary, follow-ups)
    - Properly formats roles (user/assistant) for each message
    - Preserves conversation context across multiple questions (until the Window is closed)

    2. Provider:
        Ollama (For Experts) - messages array with system prompt + history.

    3. Flow:
    a) User asks follow-up question
    b) Question is added to chat history
    c) Full history is formatted for the current provider
    d) Response is generated while maintaining context
    e) Response is displayed in chat UI
    f) New response is added to history for future context

    4. Threading:
    - Runs in a separate thread to prevent UI freezing
    - Uses signals to safely update UI from background thread
    - Handles errors too

    Args:
        response_window: The ResponseWindow instance managing the chat UI
        question: The follow-up question from the user

    This implementation is a bit convoluted, but it allows us to manage chat history & model roles across both providers! :3
    """

    def process_followup_question(self, response_window, question):
        """
        Process a follow-up question in the chat window.
        """
        logging.debug(f'Processing follow-up question: {question}')
        
        def process_thread():
            logging.debug('Starting follow-up processing thread')
            try:
                if not response_window.chat_history:
                    logging.error("No chat history found")
                    self.show_message_signal.emit('Error', 'Chat history not found')
                    return

                # Add current question to chat history
                response_window.chat_history.append({
                    "role": "user",
                    "content": question
                })
                
                # Get chat history
                history = response_window.chat_history.copy()
                
                # System instruction based on original option
                system_instruction = "You are a helpful AI assistant. Provide clear and direct responses, maintaining the same format and style as your previous responses. If appropriate, use Markdown formatting to make your response more readable."
                
                logging.debug('Sending request to AI provider')
                
                # Ollama: prepare messages with system instruction and history
                messages = [{"role": "system", "content": system_instruction}]
                for msg in history:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })

                response_text = self.current_provider.get_response(
                    system_instruction,
                    messages,
                    return_response=True
                )

                logging.debug(f'Got response of length: {len(response_text)}')
                
                # Add response to chat history
                response_window.chat_history.append({
                    "role": "assistant",
                    "content": response_text
                })
                
                # Emit response via signal
                self.followup_response_signal.emit(response_text)

            except Exception as e:
                logging.error(f'Error processing follow-up question: {e}', exc_info=True)

                if "Resource has been exhausted" in str(e):
                    self.show_message_signal.emit('Error - Rate Limit Hit', 'Whoops! You\'ve hit the per-minute rate limit of the Gemini API. Please try again in a few moments.\n\nIf this happens often, simply switch to a Gemini model with a higher usage limit in Settings.')
                    self.followup_response_signal.emit("Sorry, an error occurred while processing your question.")
                else:
                    self.show_message_signal.emit('Error', f'An error occurred: {e}')
                    self.followup_response_signal.emit("Sorry, an error occurred while processing your question.")

        # Start the thread
        threading.Thread(target=process_thread, daemon=True).start()

    def show_settings(self, providers_only=False):

        """
        Show the settings window.
        """
        logging.debug('Showing settings window')
        # Always create a new settings window to handle providers_only correctly
        self.settings_window = ui.SettingsWindow.SettingsWindow(self, providers_only=providers_only)
        self.settings_window.close_signal.connect(self.exit_app)
        self.settings_window.retranslate_ui()
        self.settings_window.show()


    def show_about(self):
        """
        Show the about window.
        """
        logging.debug('Showing about window')
        if not self.about_window:
            self.about_window = ui.AboutWindow.AboutWindow()
        self.about_window.show()

    def setup_ctrl_c_listener(self):
        """
        Listener for Ctrl+C to exit the app.
        """
        signal.signal(signal.SIGINT, lambda signum, frame: self.handle_sigint(signum, frame))
        # This empty timer is needed to make sure that the sigint handler gets checked inside the main loop:
        # without it, the sigint handle would trigger only when an event is triggered, either by a hotkey combination
        # or by another GUI event like spawning a new window. With this we trigger it every 100ms with an empy lambda
        # so that the signal handler gets checked regularly.
        self.ctrl_c_timer = QtCore.QTimer()
        self.ctrl_c_timer.start(100)
        self.ctrl_c_timer.timeout.connect(lambda: None)
    def handle_sigint(self, signum, frame):
        """
        Handle the SIGINT signal (Ctrl+C) to exit the app gracefully.
        """
        logging.info("Received SIGINT. Exiting...")
        self.exit_app()

    def exit_app(self):
        """
        Exit the application.
        """
        logging.debug('Stopping the listener')
        if self.hotkey_listener is not None:
            self.hotkey_listener.stop()
        logging.debug('Exiting application')
        self.quit()
