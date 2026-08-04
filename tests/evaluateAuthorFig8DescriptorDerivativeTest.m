classdef evaluateAuthorFig8DescriptorDerivativeTest < matlab.unittest.TestCase
    %EVALUATEAUTHORFIG8DESCRIPTORDERIVATIVETEST External author-model check.

    properties (Constant)
        FrequenciesHz = [1, 50, 1000]
    end

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(projectRoot, 'src')));
        end
    end

    methods (Test, TestTags = {'Integration', 'External'})
        function testLowDampingConverterAndNetworkDerivatives(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            workspacePath = fullfile(projectRoot, 'results', 'schur', ...
                'damping-continuation', 'damping_continuation_workspace.mat');
            testCase.assertTrue(isfile(workspacePath), ...
                'Author-derived workspace must be generated before this test.');
            data = load(workspacePath, 'lowPoint', 'networkMatrix');
            models = {data.lowPoint.converterMatrix, data.networkMatrix};

            for modelIndex = 1:numel(models)
                result = evaluateDescriptorFrequencyResponseDerivatives( ...
                    models{modelIndex}, testCase.FrequenciesHz);
                testCase.verifyTrue(all(result.numericStatus == ...
                    "resolved-double-precision"));
                testCase.verifyLessThan(max(result.primalSolveResidual), 1e-12);
                testCase.verifyLessThan(max( ...
                    result.derivativeSolveResidual), 1e-12);
                for index = 1:numel(testCase.FrequenciesHz)
                    frequencyHz = testCase.FrequenciesHz(index);
                    stepHz = max(1e-6, 1e-5*frequencyHz);
                    nearby = evaluateDescriptorFrequencyResponseDerivatives( ...
                        models{modelIndex}, ...
                        frequencyHz+[-stepHz, stepHz]);
                    finiteDifference = (nearby.response(:, :, 2)- ...
                        nearby.response(:, :, 1))/(2*stepHz);
                    relativeError = norm( ...
                        result.derivativePerHz(:, :, index)- ...
                        finiteDifference, 2)/max(norm( ...
                        result.derivativePerHz(:, :, index), 2), eps);
                    testCase.verifyLessThan(relativeError, 1e-6);
                end
            end
        end
    end
end
