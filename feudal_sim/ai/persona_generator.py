"""
Name and persona generator for AI agents using LLM calls.

Generates contextually appropriate names and personas for AI agents based on their role,
falling back to predefined options when LLM generation is not available.
"""

import os
import random
from typing import Tuple
from dataclasses import dataclass
from feudal_sim.ai.prompts import AgentType
from feudal_sim.core.config import config


@dataclass
class AgentIdentity:
    """Structured output schema for agent identity generation."""
    name: str
    persona: str


def generate_agent_identity(agent_type: AgentType, house_name: str = None) -> Tuple[str, str]:
    """
    Generate both a name and persona for an AI agent in one coherent operation.
    
    Args:
        agent_type: The type of agent (HOUSE_LORD, SCOUT, GENERAL, etc.)
        house_name: Optional house name for context (e.g., "Stark", "Lannister")
        
    Returns:
        Tuple of (agent_name, persona)
    """
    # Check for well-known personas first
    if house_name and house_name in _get_known_personas():
        known = _get_known_personas()[house_name]
        # Extract name from known persona (simple approach)
        if "Lord Eddard Stark" in known:
            return "Lord Eddard Stark", known
        elif "Lord Tywin Lannister" in known:
            return "Lord Tywin Lannister", known
        elif "Targaryen" in known:
            return f"Lord/Lady of House {house_name}", known
        elif "Robert Baratheon" in known:
            return "Robert Baratheon", known
    
    # Try LLM generation if API key is available
    if os.getenv('OPENAI_API_KEY') and config.get('simulation.ai.identity_generation.enabled', True):
        try:
            return _generate_identity_with_llm(agent_type, house_name)
        except Exception as e:
            print(f"⚠️  Identity generation failed, using fallback: {e}")
    
    # Fallback to predefined identities
    return _get_fallback_identity(agent_type, house_name)




def _generate_identity_with_llm(agent_type: AgentType, house_name: str = None) -> Tuple[str, str]:
    """Generate both name and persona using OpenAI structured outputs."""
    try:
        import openai
        from pydantic import BaseModel
        
        # Define structured output schema
        class AgentIdentitySchema(BaseModel):
            name: str
            persona: str
        
        client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        prompt = _build_identity_generation_prompt(agent_type, house_name)
        
        response = client.beta.chat.completions.parse(
            model=config.get('simulation.ai.identity_generation.model', 'gpt-4o-mini'),
            messages=[
                {"role": "system", "content": "You are a creative writer specializing in medieval fantasy character development. Generate coherent name-persona pairs."},
                {"role": "user", "content": prompt}
            ],
            response_format=AgentIdentitySchema,
            temperature=0.7
        )
        
        identity = response.choices[0].message.parsed
        print(f"🎭 Generated LLM identity: {identity.name} with matching persona ({agent_type.value})")
        return identity.name, identity.persona
        
    except ImportError:
        raise Exception("OpenAI library not available")
    except Exception as e:
        raise Exception(f"LLM identity generation error: {e}")


def _get_fallback_identity(agent_type: AgentType, house_name: str = None) -> Tuple[str, str]:
    """Get a coherent fallback name and persona pair."""
    name = _get_fallback_name(agent_type, house_name)
    persona = _get_fallback_persona(name, agent_type, house_name)
    return name, persona




def _build_identity_generation_prompt(agent_type: AgentType, house_name: str = None) -> str:
    """Build the prompt for LLM identity generation (name + persona together)."""
    
    role_descriptions = {
        AgentType.HOUSE_LORD: "a noble lord or lady ruling their house and lands",
        AgentType.SCOUT: "a skilled scout who gathers intelligence and explores the realm",
        AgentType.GENERAL: "a military commander leading armies and planning battles",
        AgentType.MERCHANT: "a wealthy trader managing commerce and trade routes",
        AgentType.DIPLOMAT: "a diplomatic envoy negotiating between houses"
    }
    
    role_desc = role_descriptions.get(agent_type, "a noble character")
    
    house_context = ""
    if house_name:
        house_context = f" of House {house_name}"
    
    return f"""Generate a cohesive medieval fantasy identity for {role_desc}{house_context}.

Requirements:
- Create a name that fits the medieval setting and reflects the character's role
- Write a matching persona in second person ("You are...")
- Ensure the name and persona work together harmoniously
- Keep persona to 2-3 sentences
- Include personality traits, values, and motivations
- Format persona as: **Your Identity:** followed by the description

The name should:
- Use medieval/fantasy naming conventions
- Reflect the character's status and role
- Consider house context if provided
- Examples: "Ser Marcus", "Lady Elara", "Roderick the Bold"

The persona should:
- Match the name's implied personality
- Include the character's role and background
- Show their values and decision-making approach
- Example: "You are Lady Elara of House Bolton, a strategic and cunning ruler..."

Generate both the name and persona now, ensuring they form a coherent character."""




def _get_fallback_name(agent_type: AgentType, house_name: str = None) -> str:
    """Get a random predefined name when LLM generation is not available."""
    
    # House-specific name pools
    house_names = {
        "Stark": ["Eddard", "Catelyn", "Brandon", "Lyanna", "Benjen", "Arya", "Sansa", "Bran", "Rickon"],
        "Lannister": ["Tywin", "Cersei", "Jaime", "Tyrion", "Kevan", "Lancel", "Myrcella", "Tommen"],
        "Targaryen": ["Daenerys", "Viserys", "Rhaegar", "Aerys", "Rhaenys", "Aegon", "Maester"],
        "Baratheon": ["Robert", "Stannis", "Renly", "Gendry", "Shireen", "Selyse"]
    }
    
    # Generic medieval names by role
    role_names = {
        AgentType.HOUSE_LORD: ["Lord Aldric", "Lady Morwyn", "Ser Gareth", "Lady Alysanne", "Lord Roderick", "Lady Elara"],
        AgentType.SCOUT: ["Marcus", "Theon", "Gareth", "Jojen", "Meera", "Osha", "Hodor"],
        AgentType.GENERAL: ["Ser Barristan", "Ser Jorah", "Ser Bronn", "Ser Davos", "Blackfish", "Greatjon"],
        AgentType.MERCHANT: ["Petyr", "Olenna", "Varys", "Illyrio", "Xaro", "Tycho"],
        AgentType.DIPLOMAT: ["Tyrion", "Samwell", "Maester Luwin", "Grand Maester", "Qyburn", "Oberyn"]
    }
    
    if house_name and house_name in house_names:
        return random.choice(house_names[house_name])
    
    return random.choice(role_names.get(agent_type, role_names[AgentType.HOUSE_LORD]))


def _get_known_personas() -> dict:
    """Get predefined personas for well-known houses."""
    return {
        "Stark": """
**Your Identity:**
You are Lord Eddard Stark, honorable ruler of Winterfell. You value honor above all else, protect your family and the North, and are wary of southern politics. You make decisions based on duty and justice, always considering what is right over what is profitable.""",
        
        "Lannister": """
**Your Identity:**
You are Lord Tywin Lannister, cunning ruler of Casterly Rock. You are strategic, wealthy, and ruthless when necessary. You believe in the power of gold and legacy, making calculated decisions for House Lannister's advantage. A Lannister always pays their debts.""",
        
        "Targaryen": """
**Your Identity:**
You are a Targaryen, heir to the dragon lords of old Valyria. You possess an innate sense of destiny and superiority, believing in your divine right to rule. You are passionate and decisive, sometimes prone to extremes, but always magnificent in your ambitions.""",
        
        "Baratheon": """
**Your Identity:**
You are Robert Baratheon, powerful lord of Storm's End. You are bold, direct, and strong-willed, preferring action to lengthy deliberation. You value loyalty and strength, ruling through personal charisma and the force of your convictions."""
    }


def _get_fallback_persona(name: str, agent_type: AgentType, house_name: str = None) -> str:
    """Get template persona when LLM generation is not available."""
    
    house_context = f" of House {house_name}" if house_name else ""
    
    # Generate role-specific default personas
    role_defaults = {
        AgentType.HOUSE_LORD: f"""
**Your Identity:**
You are {name}{house_context}, a capable ruler who must balance the needs of your people, resources, and territory while navigating the complex politics of the realm. You govern with wisdom and strength, always considering the legacy you leave for future generations.""",
        
        AgentType.SCOUT: f"""
**Your Identity:**
You are {name}, a skilled scout in service to your house. You are observant, cautious, and quick-thinking, with keen eyes for danger and opportunity. You take pride in your ability to gather vital intelligence while remaining unseen and unheard.""",
        
        AgentType.GENERAL: f"""
**Your Identity:**
You are {name}, a seasoned military commander. You are strategic, disciplined, and decisive, understanding that lives depend on your tactical wisdom. You balance aggression with prudence, always seeking victory while preserving your forces.""",
        
        AgentType.MERCHANT: f"""
**Your Identity:**
You are {name}, a prosperous merchant with extensive trade connections. You are shrewd, opportunistic, and diplomatic, seeing profit potential where others see only risk. You believe that commerce builds stronger bonds than warfare.""",
        
        AgentType.DIPLOMAT: f"""
**Your Identity:**
You are {name}, a skilled diplomatic envoy. You are eloquent, perceptive, and tactful, able to navigate delicate negotiations with grace. You understand that words can achieve what swords cannot, and that lasting peace serves all interests."""
    }
    
    return role_defaults.get(agent_type, role_defaults[AgentType.HOUSE_LORD])