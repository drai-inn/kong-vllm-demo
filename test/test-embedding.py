from openai import OpenAI

def main():
    client = OpenAI(
        base_url="https://llm.test.drai.auckland.ac.nz/embedding/v1",
    )

    response = client.embeddings.create(
        input="Your text string goes here",
        model="Qwen3-VL-Embedding-2B"
    )

    print(response.data[0].embedding)


if __name__ == "__main__":
    main()
