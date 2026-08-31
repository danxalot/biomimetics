import re

def classify_intent(text_sample, filename):
    """
    Decides if a document is 'Immutable Reality' (Logs/Config) 
    or 'Evolutionary Research' (Proposals/Theory).
    """
    # 1. Check for Log/System Indicators (IPs, Timestamps)
    if re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', text_sample): 
        return "REALITY_CHECK"
    
    system_keywords = ["config", "log", "trace", "telemetry", "k8s", "docker-compose"]
    if any(k in filename.lower() for k in system_keywords):
        return "REALITY_CHECK"

    # 2. Check for Abstract/Research Indicators
    research_keywords = ["proposal", "architecture", "future", "concept", "abstract", "whitepaper"]
    if any(k in text_sample.lower() for k in research_keywords):
        return "EVOLUTION_ANALYSIS"
    
    # Default to Research (Safer to analyze than to enforce)
    return "EVOLUTION_ANALYSIS"
