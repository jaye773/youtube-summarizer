"""AI model configuration and summary generation."""

import openai
from google import genai

# Model keys are what the UI sends and what cached summaries store as
# "model_used". Use provider aliases (no dated snapshots) so the provider's
# own upgrades apply; review against the provider deprecation pages:
#   https://developers.openai.com/api/docs/deprecations
#   https://aistudio.google.com/docs/deprecations
AVAILABLE_MODELS = {
    "gemini-3.5-flash-lite": {
        "provider": "google",
        "model": "gemini-3.5-flash-lite",
        "display_name": "Gemini 3.5 Flash-Lite (Fast)",
        "description": "Fastest and most cost-effective",
    },
    "gemini-3.8-flash": {
        "provider": "google",
        "model": "gemini-3.8-flash",
        "display_name": "Gemini 3.8 Flash (Balanced)",
        "description": "Most capable Flash model",
    },
    "gemini-4-argon": {
        "provider": "google",
        "model": "gemini-4-argon",
        "display_name": "Gemini 4 Argon (Advanced)",
        "description": "Google's flagship reasoning model",
    },
    "gpt-6-luna": {
        "provider": "openai",
        "model": "gpt-6-luna",
        "display_name": "GPT-6 Luna (Efficient)",
        "description": "Lowest-cost OpenAI model",
        "reasoning_effort": "low",
    },
    "gpt-6.1-terra": {
        "provider": "openai",
        "model": "gpt-6.1-terra",
        "display_name": "GPT-6.1 Terra (Fast)",
        "description": "Fast, efficient OpenAI model",
        "reasoning_effort": "low",
    },
    "gpt-6.1-sol": {
        "provider": "openai",
        "model": "gpt-6.1-sol",
        "display_name": "GPT-6.1 Sol (Advanced)",
        "description": "Near-flagship quality at lower cost",
        "reasoning_effort": "low",
    },
}

# Retired model keys -> current key. Old keys still arrive from cached
# summaries, saved clients and stale browser tabs; they are served by the
# successor instead of failing. All of these provider models shut down
# between 2026-12-01 and 2027-01-14.
LEGACY_MODEL_ALIASES = {
    "gemini-2.5-flash": "gemini-3.5-flash-lite",
    "gemini-2.5-pro": "gemini-3.8-flash",
    "gpt-5": "gpt-6.1-sol",
    "gpt-5-mini": "gpt-6.1-terra",
    "gpt-4o": "gpt-6-luna",
    "gpt-4o-mini": "gpt-6-luna",
}

DEFAULT_MODEL = "gemini-3.5-flash-lite"

# Output budget for OpenAI reasoning models. Reasoning tokens count against
# max_completion_tokens; if the budget runs out while reasoning, the answer
# comes back empty. OpenAI recommends reserving at least 25,000 tokens for
# reasoning and output; only tokens actually generated are billed.
OPENAI_MAX_COMPLETION_TOKENS = 25000


def resolve_model_key(model_key):
    """Return the current key for model_key (following legacy aliases), or None if unknown."""
    if not model_key:
        return DEFAULT_MODEL
    if model_key in AVAILABLE_MODELS:
        return model_key
    return LEGACY_MODEL_ALIASES.get(model_key)


def get_model_options():
    """Model metadata for the UI: key, provider, display name and description."""
    return [
        {
            "key": key,
            "provider": config["provider"],
            "display_name": config["display_name"],
            "description": config["description"],
        }
        for key, config in AVAILABLE_MODELS.items()
    ]


# Module-level clients, injected by app.py
gemini_client = None
openai_client = None


def create_gemini_client(api_key):
    """Create a Google GenAI client (google-genai SDK)."""
    return genai.Client(api_key=api_key)


def set_clients(gemini=None, openai_cli=None):
    """Inject AI clients from app.py to avoid circular imports."""
    global gemini_client, openai_client
    if gemini is not None:
        gemini_client = gemini
    if openai_cli is not None:
        openai_client = openai_cli


def get_summary_prompt(transcript, title):
    """Get the standardized prompt for summary generation"""
    return f"""
    **Your Role:** You are an expert content summarizer, specializing in transforming detailed video transcripts
    into a single, cohesive, and engaging audio-friendly summary. Your goal is to create a narrative that is not
    only informative but also easy for a listener to understand and retain when read aloud.

    **Your Task:** I will provide you with a transcript from a YouTube video titled "{title}".
    Your task is to synthesize this transcript into one continuous, audio-friendly summary.

    Within this summary, you must identify the 3-10 most critical points or actionable insights and seamlessly
    weave them into the narrative. You should introduce these key points using natural, conversational phrases
    that draw the listener's attention to their importance.

    **Key Constraints for the Summary:**

    * **No Markdown or Special Characters:** Do not use any text formatting like asterisks, bolding, or italics
    in your output. All emphasis must come from the words you choose and the structure of your sentences, not
    from formatting.
    * **Integrated Takeaways:** Do not create a separate bulleted list. Instead, highlight the main takeaways
    within the summary itself. Use clear signposting phrases like:
        * "The first key idea is..."
        * "This brings us to a really important point..."
        * "A critical takeaway here is that..."
        * "And this is the main thing to remember:"
    * **Clarity and Simplicity:** Use simple, everyday language. Avoid jargon and complex vocabulary. If you
    must use an acronym, state the full term first.
    * **Conversational Tone:** Write as if you were enthusiastically explaining the video to an interested
    friend. The tone should be engaging, clear, and natural.
    * **Short, Scannable Sentences:** Construct short, direct sentences. This makes the information easier
    for a listener to process and helps the audio flow better.
    * **Logical Flow & Pacing:** Ensure the summary moves logically from one idea to the next. Use short
    paragraphs to create natural pauses, giving the listener a moment to digest the information.
    * **Engaging Introduction and Conclusion:** Start with a hook that grabs the listener's interest and end
    with a concise wrap-up that reinforces the video's central message.

    **Example of Desired Output Structure:**

    (Start with a brief, engaging introduction that hooks the listener and states the video's main topic.)

    (In the next paragraph, begin explaining the video's concepts. When you reach the first main insight,
    introduce it naturally. For example: The video starts by explaining the basics of the topic. But the
    first key idea to really focus on is that you need to master the fundamentals before moving on. The
    creator emphasizes this because...)

    (Continue the summary, weaving in the other key takeaways with similar conversational signposts. Each
    point should flow smoothly into the next.)

    (Conclude with a short, memorable wrap-up that summarizes the core message and leaves the listener with
    a clear understanding of the video's value.)

    ---

    **{transcript}**"""


def generate_summary_gemini(transcript, title, model_name):
    """Generate summary using Google Gemini"""
    if not gemini_client:
        return (
            None,
            "Gemini model not available. Please set the GOOGLE_API_KEY environment variable.",
        )

    try:
        prompt = get_summary_prompt(transcript, title)
        # No max_output_tokens: thinking tokens count against that limit, and the
        # models' default thinking level is fine for summaries.
        response = gemini_client.models.generate_content(model=model_name, contents=prompt)
        if not response.text:
            return None, "Empty response from Gemini API"
        return response.text, None
    except Exception as e:
        print(f"Error calling Gemini API ({model_name}): {e}")
        return None, f"Error calling Gemini API: {e}"


def generate_summary_openai(transcript, title, model_name, reasoning_effort=None):
    """Generate summary using OpenAI"""
    if not openai_client:
        return (
            None,
            "OpenAI client not available. Please set the OPENAI_API_KEY environment variable.",
        )

    try:
        prompt = get_summary_prompt(transcript, title)

        # Prepare the base parameters
        api_params = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an expert content summarizer specializing in creating engaging, "
                        "audio-friendly summaries of YouTube videos."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": OPENAI_MAX_COMPLETION_TOKENS,
        }
        if reasoning_effort:
            api_params["reasoning_effort"] = reasoning_effort

        response = openai_client.chat.completions.create(**api_params)

        if not response.choices or not response.choices[0].message.content:
            if response.choices and response.choices[0].finish_reason == "length":
                return None, "OpenAI response hit the output token limit before producing a summary"
            return None, "Empty response from OpenAI API"

        return response.choices[0].message.content, None
    except Exception as e:
        print(f"Error calling OpenAI API ({model_name}): {e}")

        # Provide more specific error messages
        error_msg = str(e)
        if "api_key" in error_msg.lower():
            return None, "OpenAI API key is invalid or missing"
        elif "rate_limit" in error_msg.lower():
            return None, "OpenAI API rate limit exceeded"
        elif "model" in error_msg.lower() and "not found" in error_msg.lower():
            return None, f"OpenAI model '{model_name}' not found or not accessible"
        else:
            return None, f"Error calling OpenAI API: {e}"


def generate_summary(transcript, title, model_key=None):
    """Generate summary using specified model or default"""
    if not transcript:
        return None, "Cannot generate summary from empty transcript."

    resolved_key = resolve_model_key(model_key)
    if resolved_key is None:
        return (
            None,
            f"Unsupported model: {model_key}. Available models: {list(AVAILABLE_MODELS.keys())}",
        )

    model_config = AVAILABLE_MODELS[resolved_key]
    provider = model_config["provider"]
    model_name = model_config["model"]

    # Route to appropriate provider
    if provider == "google":
        return generate_summary_gemini(transcript, title, model_name)
    elif provider == "openai":
        return generate_summary_openai(
            transcript, title, model_name, reasoning_effort=model_config.get("reasoning_effort")
        )
    else:
        return None, f"Unknown provider: {provider}"
