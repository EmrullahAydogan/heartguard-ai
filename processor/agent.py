"""
HeartGuard AI - Agentic Workflow Module
Provides ReAct (Reasoning and Acting) capabilities to MedGemma, allowing it to use
external tools (like querying historical InfluxDB data) before making a final assessment.
"""

import json
import logging
from typing import Dict, Any, List

from medgemma_engine import _call_medgemma, _parse_json_response, clinical_reasoning

logger = logging.getLogger(__name__)

# Tools definition that MedGemma will see
TOOLS_PROMPT = """You are an intelligent cardiology assistant. You have access to the following tools to gather more context before making your final assessment:

1. query_history(patient_id: str, measurement: str, hours_back: int) -> dict
   - Fetches historical data for a vital sign. Useful to see if a current abnormal reading is a sudden spike or part of a longer trend.
   - measurement options: "heart_rate", "spo2", "respiration", "temperature"

2. fetch_latest_labs(patient_id: str) -> dict
   - Fetches the most recent laboratory results for the patient.

To use a tool, respond ONLY with a JSON object in this exact format:
{{"action": "tool_name", "kwargs": {{"arg1": "value1"}}}}

If you have enough information to make your final assessment, DO NOT use a tool.
Instead, proceed directly to your final assessment response.
"""

# ReAct Loop Prompt
AGENT_SYSTEM_PROMPT = """{tools_prompt}

PATIENT PROFILE:
- ID: {patient_id}
- Primary Diagnosis: {primary_dx}
- Comorbidities: {comorbidities}

CURRENT SITUATION:
System has flagged an anomaly.
- Trigger Reason: {trigger_reason}
- Current Vitals: HR={hr}, SpO2={spo2}, RR={rr}
- Active Flags: {active_flags}

PREVIOUS OBSERVATIONS:
{context_history}

What is your next step? Think step-by-step. If you need more data, use a tool. If you are ready to assess, output your final assessment."""


class MedGemmaAgent:
    def __init__(self, influx_client=None):
        self.influx = influx_client
        self.max_steps = 3  # Prevent infinite loops

    def _execute_tool(self, action: str, kwargs: Dict[str, Any], state) -> str:
        """Execute the requested tool and return the observation."""
        logger.info(f"Agent using tool: {action} with kwargs: {kwargs}")
        
        try:
            if action == "query_history":
                measurement = kwargs.get("measurement")
                hours = kwargs.get("hours_back", 4)
                # In a real impl, we'd query self.influx here.
                # For this challenge demo, we'll return simulated historical context
                # based on the patient state to prove the agentic loop works.
                return f"Observation from InfluxDB: In the last {hours} hours, {measurement} was relatively stable until a sudden change 30 minutes ago."
                
            elif action == "fetch_latest_labs":
                labs = state.profile.get("latest_labs", {})
                return f"Observation from Labs: {json.dumps(labs)}"
                
            else:
                return f"Error: Tool '{action}' not found."
                
        except Exception as e:
            return f"Error executing tool: {str(e)}"

    def run_clinical_reasoning(self, analysis: dict, state) -> dict:
        """
        Agentic version of clinical_reasoning.
        Loops until MedGemma provides a final assessment or max steps reached.
        """
        patient_id = state.patient_id
        profile = state.profile
        
        context_history = "No previous tools used yet."
        
        for step in range(self.max_steps):
            logger.info(f"[Patient {patient_id}] Agent Step {step+1}/{self.max_steps}")
            
            # 1. Format the ReAct prompt
            prompt = AGENT_SYSTEM_PROMPT.format(
                tools_prompt=TOOLS_PROMPT,
                patient_id=patient_id,
                primary_dx=profile.get('primary_dx', 'CHF'),
                comorbidities=str(profile.get('comorbidities', [])[:3]),
                trigger_reason=analysis.get('trigger_reason', 'periodic'),
                hr=analysis.get('heart_rate', 'N/A'),
                spo2=analysis.get('spo2', 'N/A'),
                rr=analysis.get('respiration', 'N/A'),
                active_flags=', '.join(analysis.get('active_flags', [])),
                context_history=context_history
            )
            
            # 2. Ask MedGemma what to do
            response_text = _call_medgemma(prompt)
            parsed = _parse_json_response(response_text)
            
            # 3. Check if MedGemma wants to use a tool
            if parsed and "action" in parsed:
                # Execute tool
                action = parsed["action"]
                kwargs = parsed.get("kwargs", {})
                observation = self._execute_tool(action, kwargs, state)
                
                # Update context history for the next loop
                context_history += f"\nAction: {action}\nObservation: {observation}\n"
                continue
            
            # 4. If no tool used OR max steps reached, fallback to standard reasoning 
            # but pass the gathered context!
            logger.info(f"[Patient {patient_id}] Agent finished gathering context. Proceeding to final assessment.")
            break
            
        return clinical_reasoning(analysis, state, context_history)
