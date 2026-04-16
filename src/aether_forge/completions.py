"""Shell completion generators for the Aether Forge CLI."""

from __future__ import annotations


_COMMANDS = [
    "validate", "artifact-compat", "artifact-migration-plan",
    "eval", "eval-pack", "promote-draft", "resume-replay",
    "scaffold-run", "scaffold-policy-sync", "scaffold-live-status",
    "generate-fast", "generate-slow",
    "wallet-create", "wallet-list", "wallet-info", "wallet-account",
    "wallet-sign-message", "wallet-sign-tx", "wallet-send-tx",
    "wallet-import", "wallet-delete", "wallet-export",
    "skills-search", "skills-add", "elsa-list", "models-list",
    "init", "doctor", "config-validate",
]

_PLANNER_MODES = [
    "heuristic", "static", "openai-compatible", "function-call",
    "anthropic", "gemini", "openai", "openrouter", "ollama",
]

_CRYPTO_ROUTERS = [
    "mock", "public-market-data", "paper-trading",
    "sim-wallet", "ows-wallet", "scaffold-live",
]


def generate_bash_completion() -> str:
    commands = " ".join(_COMMANDS)
    modes = " ".join(_PLANNER_MODES)
    routers = " ".join(_CRYPTO_ROUTERS)
    return f'''# Bash completion for forge CLI
# Add to ~/.bashrc: eval "$(forge completions bash)"
_forge_completions() {{
    local cur prev commands
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    commands="{commands}"

    case "$prev" in
        --planner-mode)
            COMPREPLY=( $(compgen -W "{modes}" -- "$cur") )
            return 0
            ;;
        --crypto-router)
            COMPREPLY=( $(compgen -W "{routers}" -- "$cur") )
            return 0
            ;;
        --memory-store)
            COMPREPLY=( $(compgen -W "memory sqlite" -- "$cur") )
            return 0
            ;;
        --provider)
            COMPREPLY=( $(compgen -W "openrouter ollama openai" -- "$cur") )
            return 0
            ;;
        --log-level)
            COMPREPLY=( $(compgen -W "DEBUG INFO WARNING ERROR" -- "$cur") )
            return 0
            ;;
    esac

    if [[ ${{COMP_CWORD}} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        return 0
    fi

    COMPREPLY=( $(compgen -f -- "$cur") )
}}
complete -F _forge_completions forge
'''


def generate_zsh_completion() -> str:
    commands_block = "\n".join(f"        '{cmd}:{cmd} command'" for cmd in _COMMANDS)
    modes = " ".join(_PLANNER_MODES)
    routers = " ".join(_CRYPTO_ROUTERS)
    return f'''#compdef forge
# Zsh completion for forge CLI
# Add to ~/.zshrc: eval "$(forge completions zsh)"
_forge() {{
    local -a commands
    commands=(
{commands_block}
    )

    _arguments -C \\
        '--version[Show version]' \\
        '-v[Verbose output]' \\
        '--log-level[Log level]:level:(DEBUG INFO WARNING ERROR)' \\
        '1:command:->cmds' \\
        '*::arg:->args'

    case $state in
        cmds)
            _describe 'command' commands
            ;;
        args)
            case $words[1] in
                eval|eval-pack|promote-draft|scaffold-run|resume-replay)
                    _arguments \\
                        '--planner-mode[Planner mode]:mode:({modes})' \\
                        '--crypto-router[Crypto router]:router:({routers})' \\
                        '--memory-store[Memory backend]:store:(memory sqlite)' \\
                        '*:file:_files'
                    ;;
                models-list)
                    _arguments \\
                        '--provider[Provider]:provider:(openrouter ollama openai)' \\
                        '--query[Filter query]:query:' \\
                        '--limit[Max results]:limit:'
                    ;;
                *)
                    _files
                    ;;
            esac
            ;;
    esac
}}
_forge
'''


def generate_fish_completion() -> str:
    lines = ["# Fish completion for forge CLI", "# Add to ~/.config/fish/completions/forge.fish"]
    for cmd in _COMMANDS:
        lines.append(f"complete -c forge -n '__fish_use_subcommand' -a '{cmd}' -d '{cmd}'")
    for mode in _PLANNER_MODES:
        lines.append(f"complete -c forge -l planner-mode -a '{mode}'")
    for router in _CRYPTO_ROUTERS:
        lines.append(f"complete -c forge -l crypto-router -a '{router}'")
    lines.append("complete -c forge -l memory-store -a 'memory sqlite'")
    lines.append("complete -c forge -l provider -a 'openrouter ollama openai'")
    lines.append("complete -c forge -l log-level -a 'DEBUG INFO WARNING ERROR'")
    return "\n".join(lines) + "\n"
