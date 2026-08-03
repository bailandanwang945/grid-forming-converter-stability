classdef runInfBusHermitianGeometryTest < matlab.unittest.TestCase
    %RUNINFBUSHERMITIANGEOMETRYTEST Tracked-fixture integration test.

    methods (TestClassSetup)
        function addExperimentFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            experimentFolder = fullfile(projectRoot, ...
                'experiments', 'geometry');
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                experimentFolder));
        end
    end

    methods (Test, TestTags = {'Integration'})
        function testPinnedAuthorResponsesProduceConsistentSummary(testCase)
            summary = run_inf_bus_hermitian_geometry();

            testCase.verifyEqual(summary.frequencyPointCountPerCase, 81);
            testCase.verifyEqual(summary.stableStrictSectorialCount, 35);
            testCase.verifyEqual(summary.unstableStrictSectorialCount, 0);
            testCase.verifyEqual(summary.classificationIndeterminateCount, 0);
            testCase.verifyEqual(summary.overallNumericalPendingCount, 0);
            testCase.verifyEqual( ...
                summary.stableMinimumNormalizedSeparationMargin, ...
                -0.43677920258718039, AbsTol=1e-12);
            testCase.verifyEqual( ...
                summary.unstableMinimumNormalizedSeparationMargin, ...
                -0.44246005427615659, AbsTol=1e-12);
        end
    end
end
