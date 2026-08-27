from base_agent import PHILIAgent

if __name__ == "__main__":
    agent = PHILIAgent()
    print(f"{agent.name} Agent - {agent.role}")
    print("Type 'quit' to exit.")
    while True:
        user_input = input("> ")
        if user_input.lower() == "quit":
            break
        if user_input.strip():
            resp = agent.process_request(user_input)
            print(f"PHILI: {resp}")
            print()
