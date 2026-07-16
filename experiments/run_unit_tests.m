function results = run_unit_tests()
%RUN_UNIT_TESTS Run the project's fast MATLAB unit tests.

    projectRoot = fileparts(fileparts(mfilename('fullpath')));
    testsFolder = fullfile(projectRoot, 'tests');

    results = runtests(testsFolder, ...
        'IncludeSubfolders', true, ...
        'Tag', 'Unit');
    disp(results);

    if any([results.Failed])
        error('gfm:tests:Failed', 'One or more unit tests failed.');
    end
end

