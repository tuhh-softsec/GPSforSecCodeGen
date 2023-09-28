import openai
import os
from time import sleep
import re

os.environ["TOKENIZERS_PARALLELISM"] = "false"

class CodeGenerator():
    def __init__(self, api_key, model="gpt-3.5-turbo") -> None:
        self.api_key = api_key
        self.model = model
    

    def generate_code(self, task_prompt, task_prompt_id):
        user_task_prompt = self.wrap_request("user", task_prompt)
        msgs = [user_task_prompt]
        openai.api_key = self.api_key
        try:
            response = openai.ChatCompletion.create(
                model = self.model,
                messages = msgs,
                temperature = 0.5,
                top_p = 0.1
            )
            if "<span " in response:
                print(f"Access error for prompt {task_prompt_id}... Waiting....")
                sleep(65)
                print("...continue...")

        except openai.error.RateLimitError:
            print(f"RateLimitError for prompt {task_prompt_id},... Waiting....")
            sleep(65)  # wait for 1 min to reset ratelimit
            print("...continue")
        except openai.error.APIError:
            print(f"API error for prompt {task_prompt_id},... Waiting....")
            sleep(180)  # wait for 1 min to reset ratelimit
            print("...continue")
        except openai.error.ServiceUnavailableError:
            print(f"Serveroverloaded for prompt {task_prompt_id}... waiting...")
            sleep(65)  # wait for 1 min to reset ratelimit
            print("...continue")
        except openai.error.Timeout:
            print(f"Timeout for prompt {task_prompt_id}... waiting...")
            sleep(65)  # wait for 1 min to reset ratelimit
            print("...continue")
        
        if response.choices:
            code = response.choices[0]["message"]["content"]
            return code
        else:
            return None



    def wrap_request(self, type, msg):
        return {"role": type, "content": msg}
    

    def write_code_to_file(self, prompt_task_id, prompt, code):
        """ Writes a given code snippet and its associated prompt to a Python file. """
        print(f"Writing code for {prompt_task_id} to file")
        output_dir = "output/code"
        os.makedirs(output_dir, exist_ok=True)  # Ensure the output directory exists
        code_blocks = re.findall(r'```python(.*?)```', code, re.DOTALL)
        filepath = os.path.join(output_dir, f"{prompt_task_id}.py")
        # filepath = f"{prompt_task_id}.py"
        print(filepath)
        try:
            f =  open(filepath, "w+", encoding='utf-8')
            # f.write(f"#Prompt: {prompt}\n")
            for block in code_blocks:
                f.write(block.strip() + '\n\n')
            #f.write(f"{code}\n")  # Adding a newline to separate code snippets
            return filepath
        except Exception as e:
            print(f"Failed to write to file: {e}")
            


if __name__ == "__main__":
    api_key = ""  # Replace with your OpenAI API key
    code_generator = CodeGenerator(api_key, "gpt-3.5-turbo")

    prompt = """
    Generate secure python code for the following task description:
    The user is prompted to enter an index of a vehicle.The user enters an index.
    The index is converted to an integer.The integer is used to access the array of vehicles.
    The vehicle at the index is printed.
    """


    generated_code = code_generator.generate_code(prompt, "1_3")
    #print("Generated Python code:")
    #print(generated_code)

    model_name = code_generator.model
    code_generator.write_code_to_file("1_3", prompt, generated_code)

