"""
Common dialog utilities for NeuronOS applications.

Provides standardized GTK4/Adwaita dialogs for consistent UX.
"""

from __future__ import annotations

from typing import Callable, Optional

try:
    from gi.repository import Gtk, Adw, GLib
    GTK_AVAILABLE = True
except ImportError:
    GTK_AVAILABLE = False
    Gtk = None
    Adw = None
    GLib = None


def show_error(
    parent,
    title: str,
    message: str,
    details: Optional[str] = None,
) -> None:
    """
    Show standardized error dialog.
    
    Args:
        parent: Parent window
        title: Error title/heading
        message: Error message body
        details: Optional technical details (shown in expander)
    """
    if not GTK_AVAILABLE:
        print(f"ERROR: {title}\n{message}")
        if details:
            print(f"Details: {details}")
        return
    
    dialog = Adw.MessageDialog(
        transient_for=parent,
        heading=title,
        body=message,
    )
    
    if details:
        expander = Gtk.Expander(label="Details")
        details_label = Gtk.Label(label=details)
        details_label.set_wrap(True)
        details_label.set_selectable(True)
        expander.set_child(details_label)
        dialog.set_extra_child(expander)
    
    dialog.add_response("ok", "OK")
    dialog.set_default_response("ok")
    dialog.present()


def show_confirmation(
    parent,
    title: str,
    message: str,
    confirm_label: str = "Confirm",
    destructive: bool = False,
    callback: Optional[Callable[[bool], None]] = None,
) -> None:
    """
    Show confirmation dialog.
    
    Args:
        parent: Parent window
        title: Dialog title/heading
        message: Dialog message body
        confirm_label: Label for confirm button
        destructive: If True, style confirm button as destructive
        callback: Called with True if confirmed, False if cancelled
    """
    if not GTK_AVAILABLE:
        print(f"CONFIRM: {title}\n{message}")
        if callback:
            callback(False)
        return
    
    dialog = Adw.MessageDialog(
        transient_for=parent,
        heading=title,
        body=message,
    )
    
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("confirm", confirm_label)
    
    if destructive:
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
    else:
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.SUGGESTED)
    
    dialog.set_default_response("cancel")
    
    if callback:
        dialog.connect("response", lambda d, r: callback(r == "confirm"))
    
    dialog.present()


def show_progress(
    parent,
    title: str,
    message: str,
    cancellable: bool = True,
    on_cancel: Optional[Callable[[], None]] = None,
):
    """
    Show progress dialog for long operations.
    
    Args:
        parent: Parent window
        title: Dialog title
        message: Initial message
        cancellable: Whether cancel button is shown
        on_cancel: Called when cancel is clicked
        
    Returns:
        ProgressDialog instance with update_progress() and close() methods
    """
    if not GTK_AVAILABLE:
        print(f"PROGRESS: {title}\n{message}")
        return _MockProgressDialog()
    
    return ProgressDialog(parent, title, message, cancellable, on_cancel)


class ProgressDialog:
    """Progress dialog for long operations."""
    
    def __init__(
        self,
        parent,
        title: str,
        message: str,
        cancellable: bool = True,
        on_cancel: Optional[Callable[[], None]] = None,
    ):
        self._window = Adw.Window(
            transient_for=parent,
            modal=True,
            title=title,
            default_width=400,
            default_height=150,
        )
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        
        self._message_label = Gtk.Label(label=message)
        self._message_label.set_wrap(True)
        box.append(self._message_label)
        
        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_show_text(True)
        box.append(self._progress_bar)
        
        if cancellable:
            cancel_btn = Gtk.Button(label="Cancel")
            cancel_btn.set_halign(Gtk.Align.CENTER)
            if on_cancel:
                cancel_btn.connect("clicked", lambda b: on_cancel())
            else:
                cancel_btn.connect("clicked", lambda b: self.close())
            box.append(cancel_btn)
        
        self._window.set_content(box)
        self._window.present()
    
    def update_progress(self, fraction: float, message: Optional[str] = None):
        """
        Update progress.
        
        Args:
            fraction: Progress from 0.0 to 1.0
            message: Optional new message
        """
        def _update():
            self._progress_bar.set_fraction(fraction)
            self._progress_bar.set_text(f"{int(fraction * 100)}%")
            if message:
                self._message_label.set_text(message)
            return False
        
        GLib.idle_add(_update)
    
    def pulse(self, message: Optional[str] = None):
        """Show indeterminate progress."""
        def _pulse():
            self._progress_bar.pulse()
            if message:
                self._message_label.set_text(message)
            return False
        
        GLib.idle_add(_pulse)
    
    def close(self):
        """Close the progress dialog."""
        def _close():
            self._window.close()
            return False
        
        GLib.idle_add(_close)


class _MockProgressDialog:
    """Mock progress dialog for non-GTK environments."""
    
    def update_progress(self, fraction: float, message: Optional[str] = None):
        print(f"Progress: {int(fraction * 100)}% - {message or ''}")
    
    def pulse(self, message: Optional[str] = None):
        print(f"Progress: ... - {message or ''}")
    
    def close(self):
        print("Progress complete")
