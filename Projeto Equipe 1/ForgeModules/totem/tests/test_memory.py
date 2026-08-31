import asyncio
import os
import shutil
from src.utils.memory_db import save_memory, get_all_memories, DB_PATH
from src.utils.chat_bridge import ChatBridge

async def main():
    print("Testing memories system...")
    
    # 1. Reset database for clean test
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass
            
    # 2. Test saving memory
    save_memory("Isaac", "Coordenador do lab G.E.R.A")
    save_memory("Neri", "Gosta de programar em C")
    
    # 3. Test retrieving
    memories = get_all_memories()
    print("Retrieved memories:", memories)
    assert len(memories) == 2, "Should have saved 2 memories"
    usernames = [m[0] for m in memories]
    assert "Isaac" in usernames and "Neri" in usernames, "Should contain both Isaac and Neri"
    
    # 4. Test ChatBridge system prompt injection
    bridge = ChatBridge()
    prompt_with_mem = bridge._get_system_prompt_with_memories()
    print("\nPrompt with memories snippet:")
    print("-" * 50)
    print(prompt_with_mem[-150:])
    print("-" * 50)
    assert "CONVERSAS ANTERIORES" in prompt_with_mem
    assert "[Isaac]" in prompt_with_mem
    
    # 5. Test parsing MEMORY line in stream
    print("\nTesting stream parser...")
    parsed_response, done = await bridge._process_stream_text(
        "EMOTION:happy\nCHUNK|2.0|happy|Ola!\nMEMORY|Carlos|Estuda ROS no laboratório\n<<END>>\n"
    )
    
    # Verify Carlos was saved
    memories_after = get_all_memories()
    print("Memories after stream processing:", memories_after)
    users = [m[0] for m in memories_after]
    assert "Carlos" in users, "Carlos should have been parsed and saved from stream!"
    
    print("\nAll memory tests PASSED successfully!")

if __name__ == "__main__":
    asyncio.run(main())
