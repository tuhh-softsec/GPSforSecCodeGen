from query_preparation.preparation import CodingTaskTemplate
from prompt_augmentation import back_translation, cloze, paraphrase, feedback_based_enhancement, open_security_enhancement
from code_generation.deepseek_coder_api_generated import CodeGenerator
from SAST_integration.bandit_scan import BanditScan
from prompt_scoring.bandit_score import PromptScoring
from config import config
from dataclasses import dataclass
from typing import List, Tuple, Optional
import logging


class OPS:
    def __init__(self):
        """Initialize the GPS (Guided Prompt Search) optimizer."""
        self.iterations = config.optimization_iterations
        self.k = config.optimization_k
        self.initial_prompts = [
            "Generate secure python code for the following task description: ",
            "Write python code for the following task description that prevents security vulnerabilities: ",
            "Generate python code that prevents all CWEs for the following task description: ",
            "Write python code for the following task description that is very secure: ",
            "Generate a secure python implementation for the following: "
        ]

        # Initialize components

        self.code_generator = CodeGenerator()  # code generation component
        # prompt augmentation components
        self.back_translate = back_translation.BackTranslation()
        self.cloze_augment = cloze.Cloze()
        self.paraphrase_augment = paraphrase.Paraphraser()
        self.feedback_enhancement = feedback_based_enhancement.FeedbackBasedEnhancement()
        self.open_security_enhancement = open_security_enhancement.OpenSecurityEnhancement()

        self.sast_scan = BanditScan()  # SAST component
        self.scoring = PromptScoring()  # prompt scoring component

        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        self.created_prompts = set()  # Using set for O(1) lookups

    def remove_duplicate_prompts(self, prompts: List[str]) -> List[str]:
        """Remove prompts that have been seen before."""
        unique_prompts = [p for p in prompts if p not in self.created_prompts]
        self.created_prompts.update(unique_prompts)
        return unique_prompts

    def calculate_prompt_fitness(self, prompt_id: str, prompt: str, dev_set: List[str]) -> int:
        """Calculate the fitness score for a single prompt based on the training set."""
        prompt_score = 0
        code_error = True
        code_error_count = 0

        task_template = CodingTaskTemplate()
        dev_set_queries = task_template.pre_template(prompt, dev_set)

        for query_num, query in enumerate(dev_set_queries, 1):
            prompt_task_id = f"{prompt_id}_{query_num}"
            error_status, score = self._process_single_query(
                query, prompt_task_id, prompt
            )

            if score is not None:
                if error_status == True:
                    code_error_count += 1
                else:
                    code_error = False
                prompt_score += score

        # Apply penalties
        if code_error_count >= 18:  # More than half contain errors
            prompt_score += 100
        if code_error:  # All contained errors
            prompt_score += 200

        self._log_prompt_score(prompt_id, prompt, prompt_score, code_error)
        return prompt_score

    def _process_single_query(
        self, query: str, query_id: str, prompt: str
    ) -> Optional[int]:
        """Process a single query and return its score."""
        code = self.code_generator.generate_code(query, query_id)
        if not code:
            self.logger.warning(f"Code generation failed for {query_id}")
            return None

        code_file_path = self.code_generator.write_code_to_file(
            query_id=query_id, query=query, code=code)
        if not code_file_path:
            self.logger.warning("Invalid code file path")
            return None

        scan_output = self.sast_scan.run_sast(
            filepath=code_file_path,
            query_id=query_id
        )

        if not scan_output:
            self.logger.warning(
                f"Invalid scan output for file {code_file_path}")
            return None

        if len(scan_output["errors"]) != 0:
            return True, 10

        processed_output = self.sast_scan.process_scan_output(
            query_id=query_id,
            prompt=prompt,
            bandit_output=scan_output
        )
        return False, self.scoring.bandit_score(query_id, processed_output)

    def augment_prompts(self, prompts: List[str], iteration: int) -> List[str]:
        """Augment the given prompts using multiple techniques."""
        augmented_prompts = []

        for prompt in prompts:
            augmented_prompts.extend(
                self._apply_augmentations(prompt, iteration))

        return self.remove_duplicate_prompts(augmented_prompts)

    def _apply_augmentations(self, prompt: str, iteration: int) -> List[str]:
        """Apply all augmentation techniques to a single prompt."""
        results = []

        # Back translation
        for lang in self.back_translate.languages:
            try:
                translated = self.back_translate.augment_prompt(
                    prompt=prompt,
                    source_lang='en',
                    target_lang=lang
                )
                if isinstance(translated, str):
                    results.append(translated)
            except Exception as e:
                self.logger.error(f"Back translation failed: {str(e)}")

        # Cloze augmentation
        for _ in range(4):
            try:
                clozed = self.cloze_augment.augment_prompt(prompt)
                if isinstance(clozed, str):
                    results.append(clozed)
            except Exception as e:
                self.logger.error(f"Cloze augmentation failed: {str(e)}")

        # Paraphrase augmentation
        try:
            paraphrased = self.paraphrase_augment.augment_prompt(
                prompt=prompt,
                num_beams=5,
                num_return_sequences=5
            )
            results.extend([p for p in paraphrased if isinstance(p, str)])
        except Exception as e:
            self.logger.error(f"Paraphrase augmentation failed: {str(e)}")

        try:
            feedback_enhanced = self.feedback_enhancement.augment_prompt(
                prompt=prompt,
                num_variations=4
            )
            results.extend(feedback_enhanced)
        except Exception as e:
            self.logger.error(f"Feedback enhancement failed: {str(e)}")

        try:
            open_security_enhanced = self.open_security_enhancement.augment_prompt(
                prompt=prompt,
                num_variations=4
            )
            results.extend(open_security_enhanced)
        except Exception as e:
            self.logger.error(f"Open security enhancement failed: {str(e)}")

        return results

    def optimize(self, dev_set: List[str]) -> List[Tuple[int, str]]:
        """Run the optimization algorithm to optimize prompts."""
        self.logger.info("Starting prompt optimization")

        G_t = self.initial_prompts
        stored_G = []
        reproductive_groups = []

        for t in range(self.iterations + 1):
            self.logger.info(f"Iteration {t} in progress...")
            stored_G.append(G_t)

            # Calculate fitness scores
            scores = [
                (self.calculate_prompt_fitness(f"{t}_{i}", p, dev_set), p)
                for i, p in enumerate(G_t)
            ]

            # Select top K prompts
            reproductive_group = sorted(scores)[:self.k]
            reproductive_groups.append(reproductive_group)
            self._log_reproductive_group(t, reproductive_group)

            # Generate next generation
            top_prompts = [x[1] for x in reproductive_group]
            G_t = self.augment_prompts(top_prompts, t)

        # Select final optimal prompts
        flat_groups = [item for group in reproductive_groups for item in group]
        return sorted(flat_groups)[:5]

    def _log_prompt_score(self, prompt_id: str, prompt: str, score: int, code_error: bool):
        """Log prompt scoring information."""
        with open(config.prompts_with_scores_file, "a+") as f:
            f.write(f"{prompt_id}: {
                    prompt} - {score}, CODE_ERROR: {code_error}\n")

    def _log_reproductive_group(self, iteration: int, group: List[Tuple[int, str]]):
        """Log information about the reproductive group."""
        self.logger.info(f"Top {self.k} prompts in iteration {iteration}:")
        for score, prompt in group:
            self.logger.info(f"Prompt: {prompt}, Score: {score}")
            with open(config.reproductive_group_file, "a+") as f:
                f.write(f"Iteration {iteration}: Prompt: {
                        prompt}, Score: {score}\n")


def main():
    # Load development dataset
    with open(config.development_set_file, "r") as f:
        dev_set = f.readlines()

    # Run GPS optimization
    ops = OPS()
    optimal_prompts = ops.optimize(dev_set)

    # Save results
    with open(config.final_optimal_prompts_file, "a+") as f:
        for score, prompt in optimal_prompts:
            f.write(f"{prompt} (score: {score})\n")


if __name__ == "__main__":
    main()
