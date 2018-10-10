# A Wavenet For Speech Denoising - Dario Rethage - 19.05.2017
# Datasets.py

import util
import os
import numpy as np
import logging

class WSJ0():

    def __init__(self, config, model):

        self.model = model
        self.path = config['dataset']['path']
        self.sample_rate = config['dataset']['sample_rate']
        self.file_paths = {'train': {'a': [], 'b': []}, 'valid': {'a': [], 'b': []}, 'test': {'a': [], 'b': []}}
        self.sequences  = {'train': {'a': [], 'b': []}, 'valid': {'a': [], 'b': []}, 'test': {'a': [], 'b': []}}
        self.voice_indices  = {'train': [], 'valid': [], 'test': []}
        self.regain_factors = {'train': [], 'valid': [], 'test': []}
        self.speakers       = {'train': [], 'valid': [], 'test': []}
        self.speaker_mapping = {}
        self.batch_size = config['training']['batch_size']
        self.noise_only_percent = config['dataset']['noise_only_percent']
        self.regain = config['dataset']['regain']
        self.extract_voice = config['dataset']['extract_voice']
        self.in_memory_percentage = config['dataset']['in_memory_percentage']
        self.num_sequences_in_memory = 0
        self.condition_encode_function = util.get_condition_input_encode_func(config['model']['condition_encoding'])

    def load_dataset(self):

        print('Loading WSJ0-mix dataset...')

        with open('merl_path/tr_1.txt', 'r') as f:
            train_A = f.readlines()
            train_A = list(map(lambda _: _[:-1], train_A))
        with open('merl_path/tr_2.txt', 'r') as f:
            train_B = f.readlines()
            train_B = list(map(lambda _: _[:-1], train_B))
        with open('merl_path/cv_1.txt', 'r') as f:
            valid_A = f.readlines()
            valid_A = list(map(lambda _: _[:-1], valid_A))
        with open('merl_path/cv_2.txt', 'r') as f:
            valid_B = f.readlines()
            valid_B = list(map(lambda _: _[:-1], valid_B))
        with open('merl_path/tt_1.txt', 'r') as f:
            test_A = f.readlines()
            test_A = list(map(lambda _: _[:-1], test_A))
        with open('merl_path/tt_2.txt', 'r') as f:
            test_B = f.readlines()
            test_B = list(map(lambda _: _[:-1], test_B))

        self.file_paths['train'] = {'a':train_A, 'b':train_B}
        self.file_paths['valid'] = {'a':valid_A, 'b':valid_B}
        self.file_paths['test']  = {'a':test_A,  'b':test_B}

        for set in ['train', 'valid']:
            for spk in ['a', 'b']:
                sequences, speakers, speech_onset_offset_indices, regain_factors = \
                    self.load_directory(self.file_paths[set][spk], spk)
                # self.speakers[set] = speakers
                self.sequences[set][spk] = sequences

                # if condition == 'clean':
                #     self.voice_indices[set] = speech_onset_offset_indices
                #     self.regain_factors[set] = regain_factors
        return self

    def load_directory(self, directory_path,  spk):

        filenames = directory_path

        speakers = []
        file_paths = []
        speech_onset_offset_indices = []
        regain_factors = []
        sequences = []
        for filename in filenames:
            speaker_name = filename.split('/')[-1].split('_')[0][:3] if spk=='a' else \
                           filename.split('/')[-1].split('_')[2][:3]
            if speaker_name not in speakers:
                speakers.append(speaker_name)
            sequence = util.load_wav(filename, self.sample_rate)
            sequences.append(sequence)
            self.num_sequences_in_memory += 1
            # regain_factors.append(self.regain / util.rms(sequence))

            if self.extract_voice:
                # get sub-sequence without front and ending silence
                speech_onset_offset_indices.append(util.get_subsequence_with_speech_indices(sequence))

            if speaker_name not in self.speaker_mapping:
                self.speaker_mapping[speaker_name] = len(self.speaker_mapping) + 1

        return sequences, speakers, speech_onset_offset_indices, regain_factors

    def get_num_sequences_in_dataset(self):
        return len(self.sequences['train']['a']) + len(self.sequences['train']['b']) + \
                len(self.sequences['test']['a']) + len(self.sequences['test']['b'])

    def retrieve_sequence(self, set, condition, sequence_num):

        if len(self.sequences[set][condition][sequence_num]) == 1:
            sequence = util.load_wav(self.file_paths[set][condition][sequence_num], self.sample_rate)

            if (float(self.num_sequences_in_memory) / self.get_num_sequences_in_dataset()) < self.in_memory_percentage:
                self.sequences[set][condition][sequence_num] = sequence
                self.num_sequences_in_memory += 1
        else:
            sequence = self.sequences[set][condition][sequence_num]

        return np.array(sequence)

    def get_random_batch_generator(self, set, shuffle=True):

        if set not in ['train', 'valid', 'test']:
            raise ValueError("Argument SET must be either 'train' or 'test'")

        n_data = {'train':20000,'valid':5000,'test':3000}

        indices = np.arange((n_data[set] + self.batch_size - 1) // self.batch_size * self.batch_size)
        indices %= n_data[set]
        if shuffle:
            np.random.shuffle(indices)

        beg = 0
        while True:
            sample_indices = indices[beg:beg+self.batch_size]
            beg += self.batch_size
            condition_inputs = []
            batch_inputs = []
            batch_outputs_1 = []
            batch_outputs_2 = []
            batch_out = []

            for i, sample_i in enumerate(sample_indices):
                speech_a = self.retrieve_sequence(set, 'a', sample_i)
                speech_b = self.retrieve_sequence(set, 'b', sample_i)

                mix = speech_a + speech_b

                offset = np.squeeze(np.random.randint(0, len(mix) - self.model.input_length, 1))

                output_a = speech_a[offset:offset + self.model.input_length]
                output_b = speech_b[offset:offset + self.model.input_length]
                input = mix[offset:offset + self.model.input_length]


                # if self.noise_only_percent > 0:
                #     if np.random.uniform(0, 1) <= self.noise_only_percent:
                #         input = output_noise #Noise only
                #         output_speech = np.array([0] * self.model.input_length) #Silence

                batch_inputs.append(input)
                batch_out.append([output_a, output_b])
                batch_outputs_1.append(output_a)
                batch_outputs_2.append(output_b)
                # if np.random.uniform(0, 1) <= 1.0 / self.get_num_condition_classes():
                #     condition_input = 0
                # else:
                #     condition_input = self.speaker_mapping[self.speakers[set][sample_i]]
                #     if condition_input > 28: #If speaker is in test set, use wildcard condition class 0
                #         condition_input = 0

                # condition_inputs.append(condition_input)

            batch_inputs = np.array(batch_inputs, dtype='float32')
            batch_outputs_1 = np.array(batch_outputs_1, dtype='float32')
            batch_outputs_2 = np.array(batch_outputs_2, dtype='float32')
            batch_outputs_1 = batch_outputs_1[:, self.model.get_padded_target_field_indices()]
            batch_outputs_2 = batch_outputs_2[:, self.model.get_padded_target_field_indices()]
            batch_out = np.array(batch_out, dtype='float32')
            batch_out = batch_out[:, :, self.model.get_padded_target_field_indices()]
            # condition_inputs = self.condition_encode_function(np.array(condition_inputs, dtype='uint8'), 
                                                             # self.model.num_condition_classes)

            # batch = {'data_input': batch_inputs}, {
                # 'data_output_1': batch_outputs_1, 'data_output_2': batch_outputs_2}
            batch = {'data_input': batch_inputs}, {'data_output': batch_out}
            yield batch

    def get_condition_input_encode_func(self, representation):

        if representation == 'binary':
            return util.binary_encode
        else:
            return util.one_hot_encode

    def get_num_condition_classes(self):
        return 29

    def get_target_sample_index(self):
        return int(np.floor(self.fragment_length / 2.0))

    def get_samples_of_interest_indices(self, causal=False):

        if causal:
            return -1
        else:
            target_sample_index = self.get_target_sample_index()
            return range(target_sample_index - self.half_target_field_length - self.target_padding,
                         target_sample_index + self.half_target_field_length + self.target_padding + 1)

    def get_sample_weight_vector_length(self):
        if self.samples_of_interest_only:
            return len(self.get_samples_of_interest_indices())
        else:
            return self.fragment_length
