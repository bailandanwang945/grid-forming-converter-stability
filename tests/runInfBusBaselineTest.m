classdef runInfBusBaselineTest < matlab.unittest.TestCase
    %RUNINFBUSBASELINETEST Slow integration tests for the paper baseline.

    methods (TestClassSetup)
        function addExperimentFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            experimentFolder = fullfile(projectRoot, ...
                'experiments', 'baseline');
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                experimentFolder));
        end
    end

    methods (Test, TestTags = {'Integration', 'Slow', 'External'})
        function testStableInfiniteBusCase(testCase)
            summary = run_inf_bus_baseline("stable");

            testCase.verifyTrue(summary.isClosedLoopStable);
            testCase.verifyLessThanOrEqual(summary.maximumRealPoleHz, 1e-4);
            testCase.verifyGreaterThan(summary.firstAuthorSectorialHz, 0.85);
            testCase.verifyLessThan(summary.firstAuthorSectorialHz, 1.00);
            testCase.verifyGreaterThan( ...
                summary.interpolatedMarginBoundaryHz, 0.85);
            testCase.verifyLessThan( ...
                summary.interpolatedMarginBoundaryHz, 1.00);
        end

        function testUnstableInfiniteBusCase(testCase)
            summary = run_inf_bus_baseline("unstable");

            testCase.verifyFalse(summary.isClosedLoopStable);
            testCase.verifyGreaterThan(summary.maximumRealPoleHz, 0);
            testCase.verifyGreaterThan(summary.firstAuthorSectorialHz, 1);
        end
    end
end
