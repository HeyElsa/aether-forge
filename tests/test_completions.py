from aether_forge.completions import generate_bash_completion, generate_zsh_completion, generate_fish_completion

def test_bash_completion_contains_commands():
    script = generate_bash_completion()
    assert "validate" in script
    assert "generate-fast" in script
    assert "models-list" in script
    assert "complete -F" in script

def test_zsh_completion_contains_commands():
    script = generate_zsh_completion()
    assert "#compdef forge" in script
    assert "validate" in script

def test_fish_completion_contains_commands():
    script = generate_fish_completion()
    assert "complete -c forge" in script
    assert "validate" in script
