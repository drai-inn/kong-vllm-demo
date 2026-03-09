from openai import OpenAI


def main():
    client = OpenAI(
        base_url="https://llm.test.drai.auckland.ac.nz/v1",
    )

    completion = client.chat.completions.create(
        model="Qwen3.5-35B-A3B",
        messages=[
            {"role": "system", "content": "Talk like a pirate."},
            {
                "role": "user",
                "content": "How do I check if a Python object is an instance of a class?",
            },
        ],
    )

    print(completion.choices[0].message.content)


if __name__ == "__main__":
    main()
