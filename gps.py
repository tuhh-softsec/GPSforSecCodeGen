from data_preparation.preparation import CodingTaskTemplate
from prompt_augmentation import back_translation, cloze, paraphrase
from code_generation.chatGPT_generated import CodeGenerator
from SAST_integration.bandit_Scan import BanditScan
from prompt_scoring.scoring import PromptScoring


API_KEY = ""
back_translate = back_translation.BackTranslation()
cloze_augment = cloze.Cloze()
paraphrase_augment = paraphrase.Paraphraser()
bandit_scan = BanditScan()
code_generator = CodeGenerator(API_KEY)
scoring = PromptScoring()



def f_gps(prompt_id, prompt, D_dev):
    """ calculate the fitness of a prompt based on Ddev dataset """ 
    
    # the final prompt score calculated over D_dev set
    prompt_score = 0
    template_number = 1
    bandit_scan.bandit_output_dict[prompt_id] = []
    # joining the preprompt with the code tasks in the D_dev
    template = CodingTaskTemplate()
    D_dev_task_templates = template.pre_template(D_dev)

    # calculate score for each code task in D_dev and sum it up
    for template in D_dev_task_templates:
        # generate code for the task template
        code = code_generator.generate_code(template)
        prompt_task_id = f"{prompt_id}_{template_number}"
        template_number += 1
        if code:
            # write the generated code to a python file
            code_file_path = code_generator.write_code_to_file(prompt_task_id, prompt, code)
            if code_file_path:
                # perform bandit scan on the generated python file
                scan_output = bandit_scan.run_bandit(filepath=code_file_path)
                # add the scan output to the dictionary containing several prompt score infromation
                if scan_output:
                    processed_bandit_output = bandit_scan.process_scan_output(prompt_id=prompt_id, prompt=prompt, bandit_output=scan_output)
                    score = scoring.bandit_score(prompt_id, processed_bandit_output)
                    if isinstance(score, int):
                        prompt_score += score
                    else:
                        print(f"Prompt score is invalid for prompt: {prompt_id}")
                else:
                    print(f"Invalid scan output for file {code_file_path}")
            else:
                print("Invalid code file path")
        else:
            print(f"Code generation failed for {prompt_task_id}")

    return prompt_score
        

def g_gps(prompts_to_augment):
    """ function to perform prompt augmentation"""
    augmented_prompts = []
    for prompt in prompts_to_augment:
        for lang in back_translate.languages:
            try:
                translated_prompt = back_translate.augment_prompt(prompt=prompt, source_lang='en', target_lang=lang)
            except Exception as error:
                print(f"An error occurred during back translation of prompt '{prompt}'. Error: {error}")
            if isinstance(translated_prompt, str):
                augmented_prompts.append(translated_prompt)
        for i in range(4):
            try: 
                clozed_prompt = cloze_augment.augment_prompt(prompt)
            except Exception as error:
                print(f"An error occured while performing cloze style augmentation of prompt '{prompt}, Error: {error}")
            if isinstance(clozed_prompt, str):
                augmented_prompts.append(clozed_prompt)
        try:
            paraphrased_prompts = paraphrase_augment.augment_prompt(prompt=prompt, num_beams=5, num_return_sequences=5)   
        except Exception as error:
            print(f"An error occured while paraphrasing the prompt '{prompt}, Error: {error}")
        for p in paraphrased_prompts:
            if isinstance(p, str):
                augmented_prompts.append(p)

    unique_prompts = paraphrase_augment.remove_duplicate_prompts(prompts=augmented_prompts)
    return unique_prompts

def GPS_algorithm(G_0, Ddev, T, K):
    """ method implementing the GPS algorithm"""
    G_t = G_0
    stored_G = []
    reproductive_groups = []

    
    for t in range(T+1):
        print(f"Iteration {t} in progress...")
        stored_G.append(G_t)
        
        # Calculate score for each prompt using fGPS
        scores = [f_gps(f"{t}_{index}", prompt, Ddev) for index, prompt in enumerate(G_t)]
        
        # Select top K prompts as reproductive group along with their scores
        reproductive_group = sorted(zip(scores, G_t))[:K]
        print(f"Top {K} prompts in iteration {t}:")
        for score, prompt in reproductive_group:
            print(f"Prompt: {prompt}, Score: {score} \n")
        reproductive_groups.append(reproductive_group)
        
        # Generate G_t+1 based on reproductive group using gGPS
        top_prompts = [x[1] for x in reproductive_group]
        G_t = g_gps(top_prompts)
   
    # Step 8: Select top K prompts from all stored generations using gGPS
    flat_G_t = [item for sublist in reproductive_groups for item in sublist]
    sorted_flat_G_t = sorted(flat_G_t, key=lambda x: x[0])
    optimal_prompts = sorted_flat_G_t[:K]

    # Step 9: Return the final optimized prompts
    return optimal_prompts

# Step 1: Inittial handcrafted prompts 
initial_prompts = ["Generate secure python code for the following task description: ",
                   "Write python code for the following task description that prevents security vulnerabilities: ",
                   # "Generate python code that prevents all CWEs for the following task description: ",
                   # "Write python code for the following task description that is very secure: ",
                   # "Generate a secure python implementation for the following: "
                ]


# Development dataset
with open("data/temp_developmentSet.txt", "r") as f:
    Ddev = f.readlines()

T = 2 # Number of iterations
K = 2 # Number of top prompts to select

# Run the GPS algorithm
optimized_prompts = GPS_algorithm(initial_prompts, Ddev, T, K)
print("Final optimized prompts:", optimized_prompts)
