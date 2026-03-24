DOMAIN_PRESETS: dict[str, dict[str, list[str]]] = {
    "human_preference_post_training": {
        "categories": ["cs.CL", "cs.AI", "cs.LG"],
        "include_terms": [
            "reward model",
            "process reward model",
            "outcome reward model",
            "open-ended generation",
            "writing",
            "rubric",
            "preference optimization",
            "human preference alignment",
        ],
    },
    "rl_post_training": {
        "categories": ["cs.LG", "cs.CL", "cs.AI"],
        "include_terms": ["RLHF", "GRPO", "DAPO", "DPO", "RLVR", "reasoning model"],
    },
    "agent_safety": {
        "categories": ["cs.AI", "cs.CR", "cs.CY", "cs.CL"],
        "include_terms": ["agent safety", "alignment", "oversight", "jailbreak", "governance"],
    },
    "multimodal_reasoning": {
        "categories": ["cs.CV", "cs.CL", "cs.AI", "cs.LG"],
        "include_terms": ["MLLM", "vision language model", "multimodal reasoning", "grounding"],
    },
    "rag_systems": {
        "categories": ["cs.CL", "cs.IR", "cs.AI", "cs.LG"],
        "include_terms": ["RAG", "retrieval augmented generation", "knowledge grounding"],
    },
}
