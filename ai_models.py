"""AI model configuration and summary generation."""

import google.generativeai as genai
import openai

AVAILABLE_MODELS = {
    "gemini-2.5-flash": {
        "provider": "google",
        "model": "gemini-2.5-flash-preview-05-20",
        "display_name": "Gemini 2.5 Flash (Fast)",
        "description": "Fast and efficient for most content",
    },
    "gemini-2.5-pro": {
        "provider": "google",
        "model": "gemini-2.5-pro",
        "display_name": "Gemini 2.5 Pro (Advanced)",
        "description": "More capable for complex content",
    },
    "gpt-5": {
        "provider": "openai",
        "model": "gpt-5-2025-08-07",
        "display_name": "GPT-5 (Latest)",
        "description": "OpenAI's most advanced model",
    },
    "gpt-5-mini": {
        "provider": "openai",
        "model": "gpt-5-mini-2025-08-07",
        "display_name": "GPT-5 Mini (Fast)",
        "description": "Faster GPT-5 variant",
    },
    "gpt-4o": {
        "provider": "openai",
        "model": "gpt-4o-2024-11-20",
        "display_name": "GPT-4o (Multimodal)",
        "description": "Advanced multimodal capabilities",
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "model": "gpt-4o-mini-2024-07-18",
        "display_name": "GPT-4o Mini (Efficient)",
        "description": "Fast and cost-effective",
    },
}

DEFAULT_MODEL = "gemini-2.5-flash"

# Module-level clients, injected by app.py
gemini_model = None
openai_client = None


def set_clients(gemini=None, openai_cli=None):
    """Inject AI clients from app.py to avoid circular imports."""
    global gemini_model, openai_client
    if gemini is not None:
        gemini_model = gemini
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
    if not gemini_model:
        return (
            None,
            "Gemini model not available. Please set the GOOGLE_API_KEY environment variable.",
        )

    try:
        # Create model instance for the specific model if different from default
        if model_name != "gemini-2.5-flash-preview-05-20":
            current_model = genai.GenerativeModel(model_name=model_name)
        else:
            current_model = gemini_model

        prompt = get_summary_prompt(transcript, title)
        response = current_model.generate_content(prompt)
        return response.text, None
    except Exception as e:
        print(f"Error calling Gemini API ({model_name}): {e}")
        return None, f"Error calling Gemini API: {e}"


def generate_summary_openai(transcript, title, model_name):
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
            "max_completion_tokens": 2000,
        }

        response = openai_client.chat.completions.create(**api_params)

        if not response.choices or not response.choices[0].message.content:
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

    # Use default model if none specified
    if not model_key:
        model_key = DEFAULT_MODEL

    # Validate model key
    if model_key not in AVAILABLE_MODELS:
        return (
            None,
            f"Unsupported model: {model_key}. Available models: {list(AVAILABLE_MODELS.keys())}",
        )

    model_config = AVAILABLE_MODELS[model_key]
    provider = model_config["provider"]
    model_name = model_config["model"]

    # Route to appropriate provider
    if provider == "google":
        return generate_summary_gemini(transcript, title, model_name)
    elif provider == "openai":
        return generate_summary_openai(transcript, title, model_name)
    else:
        return None, f"Unknown provider: {provider}"
