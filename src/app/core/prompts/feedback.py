"""Model-facing recovery instructions; these do not grant execution authority."""

UNVERIFIED_EXECUTION = (
    'Your previous response was rejected because it claimed command execution without a tool call. Do not '
    'repeat or paraphrase an imagined result. Use execute_command with the correct authorization_id and its '
    'real result, including the normal approval flow, or clearly state that no command was run.'
)

NEW_OPERATOR_GUIDANCE = (
    'Cancelled because the operator supplied newer guidance. Re-evaluate the task before using tools.'
)

WAITING_FOR_ANSWER = (
    "Waiting for the operator's answer."
)

MISSING_COMMAND = (
    "Command tool call missing required 'command' argument. Please provide the exact command to execute."
)

MISSING_EXPLANATION = (
    'Command not submitted. Explain its purpose and expected result in assistant text and the explanation '
    'argument before proposing it again.'
)

MISSING_QUESTION = (
    'A non-empty question is required.'
)

QUESTION_SUPERSEDED = (
    'The operator supplied newer guidance before this question was shown. Re-evaluate the task.'
)

WAITING_FOR_INPUT = (
    'Cancelled because the runtime is waiting for operator input.'
)

APPROVAL_REQUIRED = (
    'Cancelled because a previous command in the sequence required user approval.'
)

MISSING_FACT_SOURCE = (
    'Task state rejected: every verified fact must include a concise source reference.'
)

CANCELLED_BY_OPERATOR = (
    'Cancelled because the operator supplied newer guidance.'
)

TERMINAL_APPROVAL_REQUIRED = (
    'Paused because terminal access requires separate user confirmation. Wait for the terminal decision '
    'before continuing.'
)

SKILL_CHANGED = (
    'Cancelled because load_skill changed the runtime instructions. Re-evaluate before using more tools.'
)
