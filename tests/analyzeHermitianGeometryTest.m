classdef analyzeHermitianGeometryTest < matlab.unittest.TestCase
    %analyzeHermitianGeometryTest Tests for Hermitian geometry diagnostics.

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(projectRoot, 'src')));
        end
    end

    methods (Test, TestTags = {'Unit'})
        function testComplexMatrixReconstruction(testCase)
            matrix = [1+2i, 0.3-0.8i; -0.2+0.4i, -0.7+0.1i];

            result = analyzeHermitianGeometry(matrix);

            reconstructed = result.hermitianPart + ...
                1i*result.quadratureHermitianPart;
            testCase.verifyEqual(reconstructed, matrix, AbsTol=1e-14);
            testCase.verifyLessThan(result.reconstructionResidual, 1e-14);
        end

        function testBothComponentsAreHermitian(testCase)
            matrix = [1+2i, 0.3-0.8i; -0.2+0.4i, -0.7+0.1i];

            result = analyzeHermitianGeometry(matrix);

            testCase.verifyEqual( ...
                result.hermitianPart, result.hermitianPart', AbsTol=1e-14);
            testCase.verifyEqual(result.quadratureHermitianPart, ...
                result.quadratureHermitianPart', AbsTol=1e-14);
        end

        function testPositiveHermitianMatrixHasOnlyHermitianContribution(testCase)
            matrix = diag([1, 2]);

            result = analyzeHermitianGeometry(matrix);

            testCase.verifyEqual(result.normalizedSeparationMargin, 0.5, ...
                AbsTol=1e-10);
            testCase.verifyEqual(result.normalizedHermitianContribution, ...
                0.5, AbsTol=1e-10);
            testCase.verifyEqual(result.normalizedQuadratureContribution, ...
                0, AbsTol=1e-10);
        end

        function testPositiveSkewHermitianMatrixUsesQuadratureContribution(testCase)
            matrix = 1i*diag([1, 2]);

            result = analyzeHermitianGeometry(matrix);

            testCase.verifyEqual(result.normalizedSeparationMargin, 0.5, ...
                AbsTol=1e-10);
            testCase.verifyEqual(result.normalizedHermitianContribution, ...
                0, AbsTol=1e-10);
            testCase.verifyEqual(result.normalizedQuadratureContribution, ...
                0.5, AbsTol=1e-10);
        end

        function testNormalizedDiagnosticsAreScaleInvariant(testCase)
            matrix = exp(0.23i)*[1, 1.4; 0, 1];

            baseResult = analyzeHermitianGeometry(matrix);
            scaledResult = analyzeHermitianGeometry(1e6*matrix);

            testCase.verifyEqual(scaledResult.normalizedSeparationMargin, ...
                baseResult.normalizedSeparationMargin, AbsTol=1e-8);
            testCase.verifyEqual(scaledResult.normalizedCommutator, ...
                baseResult.normalizedCommutator, AbsTol=1e-8);
            testCase.verifyEqual( ...
                scaledResult.normalizedHermitianContribution, ...
                baseResult.normalizedHermitianContribution, AbsTol=1e-8);
            testCase.verifyEqual( ...
                scaledResult.normalizedQuadratureContribution, ...
                baseResult.normalizedQuadratureContribution, AbsTol=1e-8);
        end

        function testContributionsRecoverMinimumEigenvalue(testCase)
            matrix = [1+0.2i, 0.7-0.4i; -0.1+0.3i, 0.6-0.5i];

            result = analyzeHermitianGeometry(matrix);

            contributionSum = result.hermitianContribution + ...
                result.quadratureContribution;
            testCase.verifyEqual(contributionSum, result.minimumEigenvalue, ...
                AbsTol=1e-12);
            testCase.verifyLessThan(result.contributionResidual, 1e-12);
        end

        function testRepeatedMinimumEigenvalueIsNumericallyPending(testCase)
            matrix = eye(2);

            result = analyzeHermitianGeometry(matrix);

            testCase.verifyFalse(result.directionResolved);
            testCase.verifyFalse(result.isAttributionReliable);
            testCase.verifyEqual( ...
                result.attributionStatus, "numerical-pending");
            testCase.verifyEqual( ...
                result.overallNumericalStatus, "numerical-pending");
        end

        function testIndeterminateClassificationPropagatesToOverallStatus( ...
                testCase)
            matrix = [1, 2.001; 0, 1];

            result = analyzeHermitianGeometry(matrix);

            testCase.verifyEqual( ...
                result.classificationStatus, "indeterminate");
            testCase.verifyFalse(result.classification.isCertified);
            testCase.verifyEqual( ...
                result.overallNumericalStatus, "numerical-pending");
        end

        function testZeroMatrixIsNumericallyPending(testCase)
            options = struct('AbsTol', 1e-12);

            result = analyzeHermitianGeometry(zeros(2), options);

            testCase.verifyEqual( ...
                result.classification.classification, "degenerate");
            testCase.verifyFalse(result.isAttributionReliable);
            testCase.verifyTrue(isnan(result.normalizedSeparationMargin));
            testCase.verifyEqual( ...
                result.overallNumericalStatus, "numerical-pending");
        end
    end
end
