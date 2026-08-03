classdef computeStrictSectorialPhaseIntervalTest < matlab.unittest.TestCase
    %COMPUTESTRICTSECTORIALPHASEINTERVALTEST Canonical phase tests.

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(projectRoot, 'src')));
        end
    end

    methods (Test, TestTags = {'Unit'})
        function testPositiveDefiniteMatrixHasZeroPhases(testCase)
            result = computeStrictSectorialPhaseInterval(diag([1, 3]));

            testCase.verifyEqual(result.status, "resolved");
            testCase.verifyEqual(result.phases, [0; 0], AbsTol=1e-10);
            testCase.verifyEqual(result.phaseWidth, 0, AbsTol=1e-10);
        end

        function testScalarRotationShiftsAllPhases(testCase)
            alpha = 0.73;
            matrix = exp(1i*alpha)*[2, 0.4; 0.4, 1];

            result = computeStrictSectorialPhaseInterval(matrix);

            testCase.verifyEqual(result.phases, [alpha; alpha], ...
                AbsTol=1e-9);
        end

        function testKnownDiagonalPhases(testCase)
            expected = [0.4; -0.2];
            matrix = diag(exp(1i*expected));

            result = computeStrictSectorialPhaseInterval(matrix);

            testCase.verifyEqual(result.phases, expected, AbsTol=1e-9);
            testCase.verifyEqual(result.lowerPhase, -0.2, AbsTol=1e-9);
            testCase.verifyEqual(result.upperPhase, 0.4, AbsTol=1e-9);
        end

        function testNarrowIntervalAcrossPrincipalBranch(testCase)
            matrix = diag(exp(1i*deg2rad([179, -179])));

            result = computeStrictSectorialPhaseInterval(matrix);

            testCase.verifyEqual(result.status, "resolved");
            testCase.verifyEqual(result.phaseWidth, deg2rad(2), ...
                AbsTol=1e-9);
            testCase.verifyLessThanOrEqual(result.branchCenter, pi);
            testCase.verifyGreaterThanOrEqual(result.branchCenter, -pi);
        end

        function testNonSectorialMatrixIsNotApplicable(testCase)
            matrix = diag(exp(1i*[0, 2*pi/3, -2*pi/3]));

            result = computeStrictSectorialPhaseInterval(matrix);

            testCase.verifyEqual(result.status, "not-applicable");
            testCase.verifyEqual(result.reason, "non-sectorial");
            testCase.verifyTrue(isnan(result.lowerPhase));
        end

        function testOriginBoundaryDoesNotProduceUsablePhase(testCase)
            result = computeStrictSectorialPhaseInterval(diag([1, -1]));

            testCase.verifyNotEqual(result.status, "resolved");
            testCase.verifyTrue(isnan(result.lowerPhase));
        end

        function testIndeterminateClassificationRemainsPending(testCase)
            result = computeStrictSectorialPhaseInterval([1, 2.001; 0, 1]);

            testCase.verifyEqual(result.status, "numerical-pending");
            testCase.verifyEqual(result.reason, "classification-indeterminate");
        end

        function testPositiveScalingDoesNotChangePhases(testCase)
            matrix = exp(0.3i)*[1, 0.5; 0, 2];

            result = computeStrictSectorialPhaseInterval(matrix);
            scaled = computeStrictSectorialPhaseInterval(1e5*matrix);

            testCase.verifyEqual(scaled.phases, result.phases, ...
                AbsTol=1e-8);
        end

        function testCongruenceDoesNotChangePhases(testCase)
            matrix = diag(exp(1i*[0.45, -0.15]));
            transform = [2, 0.3i; -0.2, 0.7];
            congruentMatrix = transform'*matrix*transform;

            result = computeStrictSectorialPhaseInterval(matrix);
            congruent = computeStrictSectorialPhaseInterval(congruentMatrix);

            testCase.verifyEqual(congruent.phases, result.phases, ...
                AbsTol=1e-8);
        end
    end
end
