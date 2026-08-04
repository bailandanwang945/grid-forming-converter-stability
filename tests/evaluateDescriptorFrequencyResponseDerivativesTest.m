classdef evaluateDescriptorFrequencyResponseDerivativesTest < ...
        matlab.unittest.TestCase
    %EVALUATEDESCRIPTORFREQUENCYRESPONSEDERIVATIVESTEST Resolvent tests.

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(projectRoot, 'src')));
        end
    end

    methods (Test, TestTags = {'Unit'})
        function testStandardStateSpaceMatchesAnalyticFormula(testCase)
            model = testCase.firstOrderModel(1);
            frequenciesHz = [0, 1, 10];
            result = evaluateDescriptorFrequencyResponseDerivatives( ...
                model, frequenciesHz);
            omega = 2*pi*frequenciesHz;
            expectedResponse = 3+1./(2+1i*omega);
            expectedDerivative = -2*pi*1i./(2+1i*omega).^2;

            testCase.verifyEqual(squeeze(result.response).', ...
                expectedResponse, AbsTol=1e-13);
            testCase.verifyEqual(squeeze(result.derivativePerHz).', ...
                expectedDerivative, AbsTol=1e-13);
            testCase.verifyEqual(result.numericStatus, ...
                repmat("resolved-double-precision", 1, 3));
        end

        function testSingularDescriptorMatrixIsSupported(testCase)
            model = struct('A', [-2, 1; 1, 1], 'B', [1; 2], ...
                'C', [1, -1], 'D', 0.5, 'E', diag([1, 0]), ...
                'modelId', "singular-noncommuting-E-v1", ...
                'timeUnit', "seconds");
            frequenciesHz = [0, 0.4, 2];
            result = evaluateDescriptorFrequencyResponseDerivatives( ...
                model, frequenciesHz);
            omega = 2*pi*frequenciesHz;

            testCase.verifyEqual(squeeze(result.response).', ...
                2.5-2./(3+1i*omega), AbsTol=1e-13);
            testCase.verifyEqual(squeeze(result.derivativePerHz).', ...
                4*pi*1i./(3+1i*omega).^2, AbsTol=1e-13);
            testCase.verifyTrue(all(result.numericStatus == ...
                "resolved-double-precision"));
        end

        function testMatlabLtiModelUsesDescriptorData(testCase)
            model = ss(-2, 1, 1, 3);
            result = evaluateDescriptorFrequencyResponseDerivatives(model, 1);
            expected = 3+1/(2+1i*2*pi);

            testCase.verifyEqual(result.response, expected, AbsTol=1e-13);
            testCase.verifyEqual(result.modelId, "matlab-lti-model");
        end

        function testPerHzDerivativeMatchesCenteredDifference(testCase)
            model = testCase.firstOrderModel(1);
            frequencyHz = 3;
            stepHz = 1e-5;
            result = evaluateDescriptorFrequencyResponseDerivatives( ...
                model, frequencyHz);
            nearby = evaluateDescriptorFrequencyResponseDerivatives( ...
                model, frequencyHz+[-stepHz, stepHz]);
            finiteDifference = (nearby.response(:, :, 2)- ...
                nearby.response(:, :, 1))/(2*stepHz);

            testCase.verifyEqual(result.derivativePerHz, finiteDifference, ...
                RelTol=1e-9, AbsTol=1e-11);
            testCase.verifyEqual(result.derivativePerHz, ...
                2*pi*result.derivativePerRadSecond, AbsTol=1e-14);
        end

        function testDirectFeedthroughDoesNotChangeDerivative(testCase)
            withoutD = testCase.firstOrderModel(1);
            withoutD.D = 0;
            withD = withoutD;
            withD.D = 7;
            first = evaluateDescriptorFrequencyResponseDerivatives( ...
                withoutD, [0, 2]);
            second = evaluateDescriptorFrequencyResponseDerivatives( ...
                withD, [0, 2]);

            testCase.verifyEqual(second.response-first.response, ...
                7*ones(1, 1, 2), AbsTol=1e-14);
            testCase.verifyEqual(second.derivativePerHz, ...
                first.derivativePerHz, AbsTol=1e-14);
        end

        function testMimoDerivativeMatchesCenteredDifference(testCase)
            model = struct('A', [-1, 2; -3, -4], 'E', eye(2), ...
                'B', [1, 0; 0, 2], 'C', [1, 2; -1, 0.5], ...
                'D', [0.2, 0; 0, -0.1], 'modelId', "mimo-test-v1", ...
                'timeUnit', "seconds");
            frequenciesHz = [0.3, 1.7, 8]/(2*pi);
            result = evaluateDescriptorFrequencyResponseDerivatives( ...
                model, frequenciesHz);

            for index = 1:numel(frequenciesHz)
                stepHz = eps^(1/3)*max(1, frequenciesHz(index));
                nearby = evaluateDescriptorFrequencyResponseDerivatives( ...
                    model, frequenciesHz(index)+[-stepHz, stepHz]);
                finiteDifference = (nearby.response(:, :, 2)- ...
                    nearby.response(:, :, 1))/(2*stepHz);
                relativeError = norm(result.derivativePerHz(:, :, index)- ...
                    finiteDifference, 'fro')/max( ...
                    norm(finiteDifference, 'fro'), 1e-10);
                testCase.verifyLessThan(relativeError, 5e-7);
            end
        end

        function testIllConditionedPencilRemainsPending(testCase)
            model = struct('A', diag([0, -1]), 'B', eye(2), ...
                'C', eye(2), 'D', zeros(2), 'E', eye(2), ...
                'modelId', "singular-at-dc-v1", 'timeUnit', "seconds");
            result = evaluateDescriptorFrequencyResponseDerivatives( ...
                model, 0);

            testCase.verifyEqual(result.numericStatus, ...
                "numerical-pending-ill-conditioned-pencil");
            testCase.verifyTrue(all(isnan(result.response), 'all'));
        end

        function testStaticModelHasZeroDerivative(testCase)
            model = struct('A', zeros(0), 'E', zeros(0), ...
                'B', zeros(0, 1), 'C', zeros(1, 0), 'D', 2, ...
                'modelId', "static-test-v1", 'timeUnit', "seconds");
            result = evaluateDescriptorFrequencyResponseDerivatives( ...
                model, [0, 10]);

            testCase.verifyEqual(result.response, 2*ones(1, 1, 2));
            testCase.verifyEqual(result.derivativePerHz, zeros(1, 1, 2));
            testCase.verifyEqual(result.numericStatus, ...
                repmat("resolved-static", 1, 2));
        end

        function testUnsupportedLtiSemanticsAreRejected(testCase)
            milliseconds = ss(-2, 1, 1, 0);
            milliseconds.TimeUnit = 'milliseconds';
            testCase.verifyError(@() ...
                evaluateDescriptorFrequencyResponseDerivatives( ...
                    milliseconds, 1), ...
                'gfm:evaluateDescriptorFrequencyResponseDerivatives:TimeUnit');

            delayed = ss(-2, 1, 1, 0, 'InputDelay', 0.1);
            testCase.verifyError(@() ...
                evaluateDescriptorFrequencyResponseDerivatives(delayed, 1), ...
                'gfm:evaluateDescriptorFrequencyResponseDerivatives:Delay');
        end

        function testForwardErrorProxyCanHoldBackResolvedStatus(testCase)
            model = struct('A', -hilb(9), 'E', zeros(9), ...
                'B', ones(9, 1), 'C', ones(1, 9), 'D', 0, ...
                'modelId', "hilbert-forward-error-v1", ...
                'timeUnit', "seconds");
            result = evaluateDescriptorFrequencyResponseDerivatives(model, 0);

            testCase.verifyEqual(result.numericStatus, ...
                "numerical-pending-forward-error-too-large");
            testCase.verifyGreaterThan( ...
                result.estimatedRelativeForwardError, 1e-6);
        end
    end

    methods (Static, Access=private)
        function model = firstOrderModel(E)
            model = struct('A', -2, 'B', 1, 'C', 1, 'D', 3, ...
                'E', E, 'modelId', "first-order-test-v1", ...
                'timeUnit', "seconds");
        end
    end
end
