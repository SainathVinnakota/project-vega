from runtime.response_composer import ResponseComposer

def test_compose_response():
    composer = ResponseComposer()
    result = composer.compose(
        agent_id="test_agent",
        answer="Hello world",
        session_id="session-123",
        model_id="anthropic.claude-v3"
    )
    
    assert result["status"] == "success"
    assert result["answer"] == "Hello world"
    assert result["session_id"] == "session-123"
    assert result["agent_id"] == "test_agent"
    assert result["model_id"] == "anthropic.claude-v3"
    assert "citations" in result
    assert "metadata" in result
