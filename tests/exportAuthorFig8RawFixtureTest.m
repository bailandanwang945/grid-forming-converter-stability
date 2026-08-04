classdef exportAuthorFig8RawFixtureTest < matlab.unittest.TestCase
    %EXPORTAUTHORFIG8RAWFIXTURETEST Provenance-path fixture regeneration.

    methods (TestClassSetup)
        function addExperimentFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(projectRoot, 'experiments', 'baseline')));
        end
    end

    methods (Test, TestTags = {'Integration', 'Slow', 'External'})
        function testRegeneratedFixtureMatchesPinnedValues(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            sourcePath = fullfile(projectRoot, 'results', 'schur', ...
                'damping-continuation', ...
                'damping_continuation_workspace.mat');
            pinnedRoot = fullfile(projectRoot, 'experiments', ...
                'baseline', 'fixtures');
            temporaryRoot = tempname;
            mkdir(temporaryRoot);
            cleanup = onCleanup(@() rmdir(temporaryRoot, 's'));

            manifest = export_author_fig8_raw_fixture( ...
                sourcePath, temporaryRoot, struct());
            generated = readtable(fullfile(temporaryRoot, ...
                'author_fig8_raw_frequency_response.csv'), ...
                TextType='string');
            pinned = readtable(fullfile(pinnedRoot, ...
                'author_fig8_raw_frequency_response.csv'), ...
                TextType='string');
            generatedSpectrum = readtable(fullfile(temporaryRoot, ...
                'author_fig8_spectrum.csv'), TextType='string');
            pinnedSpectrum = readtable(fullfile(pinnedRoot, ...
                'author_fig8_spectrum.csv'), TextType='string');

            testCase.verifyEqual(generated.case_id, pinned.case_id);
            numericNames = string(generated.Properties.VariableNames(2:end));
            for index = 1:numel(numericNames)
                name = numericNames(index);
                testCase.verifyEqual(generated.(name), pinned.(name), ...
                    AbsTol=1e-12, RelTol=1e-12);
            end
            exactNames = ["case_id", "value_type", "value_index", ...
                "is_dominant_pair"];
            for index = 1:numel(exactNames)
                name = exactNames(index);
                testCase.verifyEqual(generatedSpectrum.(name), ...
                    pinnedSpectrum.(name));
            end
            testCase.verifyEqual(generatedSpectrum.damping_D, ...
                pinnedSpectrum.damping_D, AbsTol=1e-12);
            testCase.verifyEqual(generatedSpectrum.real_Hz, ...
                pinnedSpectrum.real_Hz, AbsTol=1e-8);
            testCase.verifyEqual(generatedSpectrum.imag_Hz, ...
                pinnedSpectrum.imag_Hz, AbsTol=1e-8);
            testCase.verifyEqual(manifest.frequencyResponseRowCount, 2000);
            testCase.verifyEqual(manifest.spectrumRowCount, 80);
            clear cleanup
        end
    end
end
