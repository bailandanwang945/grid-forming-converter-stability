classdef classifyNumericalRangeTest < matlab.unittest.TestCase
    %CLASSIFYNUMERICALRANGETEST Unit tests for classifyNumericalRange.

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            sourceFolder = fullfile(projectRoot, 'src');
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture(sourceFolder));
        end
    end

    methods (Test, TestTags = {'Unit'})
        function testStrictPositiveDefiniteMatrix(testCase)
            A = diag([1, 2]);

            result = classifyNumericalRange(A);

            testCase.verifyEqual(result.classification, "strict-sectorial");
            testCase.verifyTrue(result.isStrictSectorial);
            testCase.verifyEqual(result.margin, 1, AbsTol=1e-9);
        end

        function testRotatedStrictSectorialMatrix(testCase)
            rotationAngle = 0.317;
            A = exp(1i*rotationAngle)*diag([1, 2]);

            result = classifyNumericalRange(A);

            testCase.verifyEqual(result.classification, "strict-sectorial");
            testCase.verifyEqual(result.margin, 1, AbsTol=1e-9);
            testCase.verifyEqual(abs(angle(exp(1i*(result.theta-rotationAngle)))), ...
                0, AbsTol=1e-7);
        end

        function testBoundaryMatrix(testCase)
            A = diag([0, 2]);

            result = classifyNumericalRange(A);

            testCase.verifyEqual(result.classification, "indeterminate");
            testCase.verifyEqual(result.candidateClassification, "boundary");
            testCase.verifyFalse(result.isCertified);
            testCase.verifyLessThanOrEqual(abs(result.margin), 1e-9);
        end

        function testNonSectorialNilpotentMatrix(testCase)
            A = [0, 1; 0, 0];

            result = classifyNumericalRange(A);

            testCase.verifyEqual(result.classification, "non-sectorial");
            testCase.verifyFalse(result.isStrictSectorial);
            testCase.verifyEqual(result.margin, -0.5, AbsTol=1e-9);
        end

        function testDegenerateZeroMatrix(testCase)
            A = zeros(2);

            result = classifyNumericalRange(A);

            testCase.verifyEqual(result.classification, "degenerate");
            testCase.verifyEqual(result.scale, 0, AbsTol=0);
        end

        function testPositiveScaleInvariance(testCase)
            A = exp(-1i*pi/4)*diag([1, 3]);

            baseResult = classifyNumericalRange(A);
            largeResult = classifyNumericalRange(1e8*A);
            smallResult = classifyNumericalRange(1e-8*A);

            testCase.verifyEqual(largeResult.classification, baseResult.classification);
            testCase.verifyEqual(smallResult.classification, baseResult.classification);
            testCase.verifyEqual(largeResult.normalizedMargin, ...
                baseResult.normalizedMargin, AbsTol=1e-10);
            testCase.verifyEqual(smallResult.normalizedMargin, ...
                baseResult.normalizedMargin, AbsTol=1e-10);
        end

        function testOffGridStrictCaseWithoutRefinementIsIndeterminate(testCase)
            A = exp(1i*pi/16)*[1, 1.99; 0, 1];
            options = struct('NumAngles', 16, 'Refine', false);

            result = classifyNumericalRange(A, options);

            testCase.verifyEqual(result.classification, "indeterminate");
            testCase.verifyEqual(result.candidateClassification, "non-sectorial");
            testCase.verifyGreaterThan(result.upperBound, 0);
        end

        function testOffGridStrictCaseWithRefinementIsCertified(testCase)
            A = exp(1i*0.317)*[1, 1.99; 0, 1];

            result = classifyNumericalRange(A);

            testCase.verifyEqual(result.classification, "strict-sectorial");
            testCase.verifyTrue(result.isCertified);
            testCase.verifyEqual(result.margin, 0.005, AbsTol=1e-9);
        end

        function testAnalyticJordanBoundaryCaseIsIndeterminate(testCase)
            A = exp(1i*0.317)*[1, 2; 0, 1];

            result = classifyNumericalRange(A);

            testCase.verifyEqual(result.classification, "indeterminate");
            testCase.verifyEqual(result.candidateClassification, "boundary");
            testCase.verifyLessThanOrEqual(abs(result.margin), 1e-9);
        end

        function testAnalyticJordanNonSectorialCaseIsCertified(testCase)
            A = exp(1i*0.317)*[1, 2.2; 0, 1];

            result = classifyNumericalRange(A);

            testCase.verifyEqual(result.classification, "non-sectorial");
            testCase.verifyTrue(result.isCertified);
            testCase.verifyEqual(result.margin, -0.1, AbsTol=1e-9);
        end

        function testUnitarySimilarityInvariance(testCase)
            A = exp(1i*0.317)*[1, 1.5; 0, 1];
            U = [1, 1; -1, 1]/sqrt(2);

            baseResult = classifyNumericalRange(A);
            transformedResult = classifyNumericalRange(U'*A*U);

            testCase.verifyEqual(transformedResult.classification, ...
                baseResult.classification);
            testCase.verifyEqual(transformedResult.normalizedMargin, ...
                baseResult.normalizedMargin, AbsTol=1e-10);
        end

        function testNonSquareMatrixErrors(testCase)
            A = ones(2, 3);

            testCase.verifyError(@() classifyNumericalRange(A), ...
                'gfm:classifyNumericalRange:InvalidMatrix');
        end

        function testNonFiniteMatrixErrors(testCase)
            A = [1, NaN; 0, 1];

            testCase.verifyError(@() classifyNumericalRange(A), ...
                'gfm:classifyNumericalRange:NonFiniteMatrix');
        end

        function testInvalidAngleCountErrors(testCase)
            A = eye(2);
            options = struct('NumAngles', 8);

            testCase.verifyError(@() classifyNumericalRange(A, options), ...
                'gfm:classifyNumericalRange:InvalidNumAngles');
        end

        function testComplexAngleCountErrors(testCase)
            A = eye(2);
            options = struct('NumAngles', 16+1i);

            testCase.verifyError(@() classifyNumericalRange(A, options), ...
                'gfm:classifyNumericalRange:InvalidNumAngles');
        end

        function testComplexRelativeToleranceErrors(testCase)
            A = eye(2);
            options = struct('RelTol', 1+1i);

            testCase.verifyError(@() classifyNumericalRange(A, options), ...
                'gfm:classifyNumericalRange:InvalidTolerance');
        end

        function testComplexAbsoluteToleranceErrors(testCase)
            A = eye(2);
            options = struct('AbsTol', 1+1i);

            testCase.verifyError(@() classifyNumericalRange(A, options), ...
                'gfm:classifyNumericalRange:InvalidTolerance');
        end
    end
end
