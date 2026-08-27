from base_agent import SAMIAgent

if __name__ == "__main__":
    agent = SAMIAgent()
    print(f"{agent.name} Agent - {agent.role}")
    print("Type 'quit' to exit.")
    while True:
        user_input = input("> ")
        if user_input.lower() == "quit":
            print("Exiting SAMI Agent. Goodbye.")
            break
        if user_input.strip():
            response = agent.process_request(user_input)
            print(f"SAMI: {response}")
            print()
