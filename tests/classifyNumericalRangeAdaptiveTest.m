classdef classifyNumericalRangeAdaptiveTest < matlab.unittest.TestCase
    %CLASSIFYNUMERICALRANGEADAPTIVETEST Tests for the adaptive envelope.

    properties (TestParameter)
        jordanCase = struct( ...
            'strict', struct('k', 1.99), ...
            'boundary', struct('k', 2.00), ...
            'nonsectorial', struct('k', 2.01));
    end

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            sourceFolder = fullfile(projectRoot, 'src');
            testCase.applyFixture( ...
                matlab.unittest.fixtures.PathFixture(sourceFolder));
        end
    end

    methods (Test, TestTags = {'Unit'})
        function testStrictPositiveDefiniteMatrix(testCase)
            result = classifyNumericalRangeAdaptive(diag([1, 2]));

            testCase.verifyEqual(result.classification, "strict-sectorial");
            testCase.verifyTrue(result.isCertified);
            testCase.verifyGreaterThan(result.normalizedLowerBound, 0);
        end

        function testNilpotentMatrixIsNonSectorial(testCase)
            result = classifyNumericalRangeAdaptive([0, 1; 0, 0]);

            testCase.verifyEqual(result.classification, "non-sectorial");
            testCase.verifyTrue(result.isCertified);
            testCase.verifyEqual(result.normalizedUpperBound, -0.5, ...
                AbsTol=0.1);
        end

        function testJordanEnvelopeContainsExactMargin(testCase, jordanCase)
            A = exp(1i*0.317)*[1, jordanCase.k; 0, 1];
            exactMargin = (1-abs(jordanCase.k)/2)/norm(A, 2);
            options = struct('MaxEvaluations', 256, ...
                'OptimalityTol', 1e-8);

            result = classifyNumericalRangeAdaptive(A, options);

            testCase.verifyLessThanOrEqual( ...
                result.normalizedLowerBound, exactMargin+1e-12);
            testCase.verifyGreaterThanOrEqual( ...
                result.normalizedUpperBound, exactMargin-1e-12);
        end

        function testNearNonSectorialJordanCaseIsCertified(testCase)
            A = exp(1i*0.317)*[1, 2.01; 0, 1];
            options = struct('MaxEvaluations', 256);

            result = classifyNumericalRangeAdaptive(A, options);

            testCase.verifyEqual(result.classification, "non-sectorial");
            testCase.verifyTrue(result.isCertified);
            testCase.verifyLessThan(result.normalizedUpperBound, 0);
        end

        function testBoundaryCaseUsesToleranceBand(testCase)
            A = exp(1i*0.317)*[1, 2; 0, 1];
            options = struct('RelTol', 1e-3, ...
                'OptimalityTol', 1e-8, 'MaxEvaluations', 512);

            result = classifyNumericalRangeAdaptive(A, options);

            testCase.verifyEqual(result.classification, "boundary");
            testCase.verifyTrue(result.isCertified);
            testCase.verifyEqual(result.stopReason, "boundary-band");
        end

        function testBudgetStopRemainsIndeterminate(testCase)
            A = exp(1i*0.317)*[1, 2; 0, 1];
            options = struct('InitialIntervals', 16, ...
                'MaxEvaluations', 16, 'RelTol', 1e-12, ...
                'OptimalityTol', 1e-14);

            result = classifyNumericalRangeAdaptive(A, options);

            testCase.verifyEqual(result.classification, "indeterminate");
            testCase.verifyFalse(result.isCertified);
            testCase.verifyEqual(result.stopReason, "evaluation-budget");
            testCase.verifyEqual(result.evaluationCount, 16);
        end

        function testEnvelopeTightensWithLargerBudget(testCase)
            A = exp(1i*0.317)*[1, 2; 0, 1];
            common = struct('InitialIntervals', 16, 'RelTol', 1e-14, ...
                'OptimalityTol', 1e-14);
            smallOptions = common;
            smallOptions.MaxEvaluations = 16;
            mediumOptions = common;
            mediumOptions.MaxEvaluations = 32;
            largeOptions = common;
            largeOptions.MaxEvaluations = 64;

            smallResult = classifyNumericalRangeAdaptive(A, smallOptions);
            mediumResult = classifyNumericalRangeAdaptive(A, mediumOptions);
            largeResult = classifyNumericalRangeAdaptive(A, largeOptions);

            testCase.verifyGreaterThanOrEqual( ...
                mediumResult.normalizedLowerBound, ...
                smallResult.normalizedLowerBound-1e-14);
            testCase.verifyGreaterThanOrEqual( ...
                largeResult.normalizedLowerBound, ...
                mediumResult.normalizedLowerBound-1e-14);
            testCase.verifyLessThanOrEqual( ...
                mediumResult.normalizedUpperBound, ...
                smallResult.normalizedUpperBound+1e-14);
            testCase.verifyLessThanOrEqual( ...
                largeResult.normalizedUpperBound, ...
                mediumResult.normalizedUpperBound+1e-14);
        end

        function testPositiveScaleInvariance(testCase)
            A = exp(-1i*pi/4)*[1, 1.5; 0, 1];

            baseResult = classifyNumericalRangeAdaptive(A);
            scaledResult = classifyNumericalRangeAdaptive(1e7*A);

            testCase.verifyEqual( ...
                scaledResult.classification, baseResult.classification);
            testCase.verifyEqual(scaledResult.normalizedLowerBound, ...
                baseResult.normalizedLowerBound, AbsTol=1e-12);
            testCase.verifyEqual(scaledResult.normalizedUpperBound, ...
                baseResult.normalizedUpperBound, AbsTol=1e-12);
        end

        function testInvalidEvaluationBudgetErrors(testCase)
            options = struct('InitialIntervals', 32, 'MaxEvaluations', 31);

            testCase.verifyError( ...
                @() classifyNumericalRangeAdaptive(eye(2), options), ...
                'gfm:classifyNumericalRangeAdaptive:InvalidMaxEvaluations');
        end
    end
end
