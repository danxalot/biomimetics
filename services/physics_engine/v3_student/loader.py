from .numpy_stack import VersorMemMambaStackNP

def load_v3_student(npz_path):
    """Entry point for neural_system to load the V3 student stack."""
    print(f"[*] Loading Mamba-3 Student Stack from {npz_path}...")
    stack = VersorMemMambaStackNP(npz_path)
    print(f"[+] Load complete. 32 layers active.")
    return stack
