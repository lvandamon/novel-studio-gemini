import os
import subprocess
import tempfile
import sys

def open_in_editor(content: str, extension: str = ".txt") -> str:
    """
    Opens the given content in the system's default text editor.
    Returns the modified content after the editor is closed.
    """
    # Prefer VISUAL, then EDITOR, then 'vim', then 'nano'
    editor = os.environ.get('VISUAL') or os.environ.get('EDITOR') or 'vim'
    
    # Create a temp file
    with tempfile.NamedTemporaryFile(suffix=extension, mode='w+', delete=False, encoding='utf-8') as tf:
        tf.write(content)
        tf_path = tf.name

    try:
        # Run the editor
        # If on Windows, might need shell=True or start command, but we assume Darwin/Linux per context
        if sys.platform == "win32":
            subprocess.call([editor, tf_path], shell=True)
        else:
            # Try to run directly. If it fails (e.g. editor command not found), fallback.
            try:
                subprocess.call([editor, tf_path])
            except FileNotFoundError:
                # Fallback to nano if vim not found, or open generic
                print(f"⚠️  Editor '{editor}' not found. Trying 'nano'...")
                subprocess.call(['nano', tf_path])
        
        # Read back the file
        with open(tf_path, 'r', encoding='utf-8') as f:
            new_content = f.read()
            
    except Exception as e:
        print(f"❌ Failed to open editor: {e}")
        return content # Return original on failure
        
    finally:
        # Cleanup
        if os.path.exists(tf_path):
            os.remove(tf_path)

    return new_content
