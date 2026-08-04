classdef unwrapPhaseIntervalSamplesTest < matlab.unittest.TestCase
    %UNWRAPPHASEINTERVALSAMPLESTEST Frequency-continuous branch tests.

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(projectRoot, 'src')));
        end
    end

    methods (Test, TestTags = {'Unit'})
        function testPrincipalBranchCrossingIsUnwrapped(testCase)
            lower = deg2rad([170, -175, -160]);
            upper = lower;
            status = repmat("resolved", 1, 3);

            result = unwrapPhaseIntervalSamples( ...
                lower, upper, status, deg2rad(170), struct());

            testCase.verifyEqual(result.center, ...
                deg2rad([170, 185, 200]), AbsTol=1e-12);
            testCase.verifyEqual(result.branchStatus, ...
                repmat("resolved-under-nearest-neighbor-assumption", 1, 3));
        end

        function testThirdOrderCounterexampleCentersUnwrapContinuously(testCase)
            principalCenters = deg2rad([0, -135, 169.695, ...
                132.075, 111.447, 91.719]);
            expectedCenters = deg2rad([0, -135, -190.305, ...
                -227.925, -248.553, -268.281]);
            status = repmat("resolved", 1, 6);

            result = unwrapPhaseIntervalSamples(principalCenters, ...
                principalCenters, status, 0, struct());

            testCase.verifyEqual(result.center, expectedCenters, ...
                AbsTol=deg2rad(1e-9));
        end

        function testMissingSeedIsIndeterminate(testCase)
            result = unwrapPhaseIntervalSamples(0.2, 0.2, ...
                "resolved", NaN, struct());

            testCase.verifyEqual(result.branchStatus, ...
                "phase-branch-indeterminate");
            testCase.verifyEqual(result.reasonCodes, ...
                "phase-branch-unanchored");
        end

        function testResolvedGapMakesLaterBranchIndeterminate(testCase)
            lower = [0, NaN, 0.2];
            upper = lower;
            status = ["resolved", "numerical-pending", "resolved"];

            result = unwrapPhaseIntervalSamples( ...
                lower, upper, status, 0, struct());

            testCase.verifyEqual(result.branchStatus, ...
                ["resolved-under-nearest-neighbor-assumption", ...
                 "phase-unavailable", ...
                 "phase-branch-indeterminate"]);
            testCase.verifyEqual(result.reasonCodes(3), ...
                "phase-gap-indeterminate");
        end

        function testLeadingGapMakesLaterBranchIndeterminate(testCase)
            lower = [NaN, 0.2];
            upper = lower;
            status = ["numerical-pending", "resolved"];

            result = unwrapPhaseIntervalSamples( ...
                lower, upper, status, 0, struct());

            testCase.verifyEqual(result.branchStatus, ...
                ["phase-unavailable", "phase-branch-indeterminate"]);
            testCase.verifyEqual(result.reasonCodes(2), ...
                "phase-gap-indeterminate");
        end

        function testThreeDimensionalIntervalsAreRejected(testCase)
            lower = zeros(1, 1, 2);
            upper = lower;
            status = repmat("resolved", 1, 1, 2);

            testCase.verifyError(@() unwrapPhaseIntervalSamples( ...
                lower, upper, status, 0, struct()), ...
                'gfm:unwrapPhaseIntervalSamples:InvalidIntervals');
        end

        function testLaterExplicitSeedStartsNewCertifiedSegment(testCase)
            lower = [NaN, NaN, 0.2, 0.3];
            upper = lower;
            status = ["numerical-pending", "numerical-pending", ...
                "resolved", "resolved"];
            options = struct('SeedFrequencyIndices', 3);

            result = unwrapPhaseIntervalSamples( ...
                lower, upper, status, 0.2, options);

            testCase.verifyEqual(result.reasonCodes(1:2), ...
                repmat("phase-before-explicit-seed", 1, 2));
            testCase.verifyEqual(result.branchStatus(3:4), ...
                repmat("resolved-under-nearest-neighbor-assumption", 1, 2));
        end

        function testNearPiStepIsIndeterminate(testCase)
            lower = [0, 0.95*pi];
            upper = lower;
            status = ["resolved", "resolved"];

            result = unwrapPhaseIntervalSamples( ...
                lower, upper, status, 0, struct());

            testCase.verifyEqual(result.reasonCodes(2), ...
                "phase-step-indeterminate");
        end

        function testRowsUseIndependentSeeds(testCase)
            lower = deg2rad([170, -175; -170, 175]);
            upper = lower;
            status = repmat("resolved", 2, 2);

            result = unwrapPhaseIntervalSamples(lower, upper, status, ...
                deg2rad([170; -170]), struct());

            testCase.verifyEqual(result.center, ...
                deg2rad([170, 185; -170, -185]), AbsTol=1e-12);
        end
    end
end
