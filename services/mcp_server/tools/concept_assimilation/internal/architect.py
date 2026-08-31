class SystemArchitect:
    def __init__(self, llm_client):
        self.llm = llm_client

    def synthesize_solution(self, winning_atoms, rejected_log):
        """
        Generates the Final Master Document.
        """
        # Separate Code for Prompt Clarity
        code_blocks = [a for a in winning_atoms if a.get('code_snippet')]
        concepts = [a for a in winning_atoms if not a.get('code_snippet')]
        
        prompt = f"""
        You are ARCA, the Chief Systems Architect.
        
        **Objective:** Synthesize a "Master Architecture v2.0" from these approved components.
        
        **Approved Functional Blocks (Code Available):**
        {self._format_atoms(code_blocks, include_code=True)}
        
        **Approved Conceptual Blocks:**
        {self._format_atoms(concepts, include_code=False)}
        
        **Rejected Elements (Context):**
        {self._format_rejected(rejected_log)}
        
        **Output Requirements:**
        1. **Executive Summary:** The overall system design.
        2. **Technical Implementation:** Detailed sections. YOU MUST INSERT THE PROVIDED CODE SNIPPETS into the correct locations.
        3. **Evolution Log:** Explain why specific Future ideas replaced Current ones (refer to the Rejected Elements).
        """
        
        # Invoke LLM Client
        try:
            # The client (GatewayClient) mimics the LangChain .invoke pattern returning a string
            return self.llm.invoke(prompt)
        except Exception as e:
            return f"Error Generating Architecture: {e}"

    def _format_atoms(self, atoms, include_code=False):
        out = ""
        for a in atoms:
            out += f"- [{a.get('origin', 'UNKNOWN')}] {a['concept']}\n"
            if include_code and a.get('code_snippet'):
                # Truncate slightly to fit context window if necessary
                snippet = a['code_snippet']
                out += f"  CODE:\n{snippet}\n"
        return out

    def _format_rejected(self, log):
        out = ""
        for r in log:
            out += f"- Rejected {r['id']} (Cost: {r.get('cost_metric', 0):.2f}): {r.get('reason', 'Unknown')}\n"
        return out
